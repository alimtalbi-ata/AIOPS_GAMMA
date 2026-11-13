"""Opt-in REAL PostgreSQL replay concurrency tests.

Run only against an isolated disposable DB with migration 0002 applied:
    GAMMA_REPLAY_TEST_ALLOW_WRITE=I_UNDERSTAND_DISPOSABLE_DB \\
    GAMMA_REPLAY_TEST_DATABASE_URL=postgresql+asyncpg://... pytest -q tests/test_gateway_replay_postgres.py

Never point this at staging/production; tests write replay reservations.
"""
import asyncio
import hashlib
import os
import time
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway_replay import consume_assertion_before_access


def _require_disposable_database_url(raw_url: str) -> str:
    if not raw_url:
        pytest.skip("No disposable PostgreSQL test URL configured")
    parsed = make_url(raw_url)
    if parsed.drivername != "postgresql+asyncpg":
        pytest.fail("Replay integration test requires postgresql+asyncpg URL")
    if not parsed.database or not parsed.database.endswith("_replay_test"):
        pytest.fail("Replay tests require a database named *_replay_test")
    if parsed.host not in ("localhost", "127.0.0.1", "::1"):
        pytest.fail("Replay tests require loopback PostgreSQL; use a local disposable instance")
    # asyncpg/SQLAlchemy URL query options can override connection routing
    # (e.g. ?host=remote.example or Unix socket paths). Reject them entirely.
    if parsed.query:
        pytest.fail("Replay tests reject URL query options that may override routing")
    return raw_url


@pytest_asyncio.fixture
async def replay_db():
    url = _require_disposable_database_url(
        os.environ.get("GAMMA_REPLAY_TEST_DATABASE_URL", "")
    )
    if os.environ.get("GAMMA_REPLAY_TEST_ALLOW_WRITE") != "I_UNDERSTAND_DISPOSABLE_DB":
        pytest.fail("Explicit disposable database write acknowledgement required")
    engine = create_async_engine(url, pool_size=4, max_overflow=0)
    try:
        async with engine.connect() as connection:
            # Verify the connected DB identity as well as the URL before writes.
            db_name = await connection.scalar(text("SELECT current_database()"))
            assert db_name and db_name.endswith("_replay_test"), "Unsafe database identity"
            server_version = await connection.scalar(text("SHOW server_version_num"))
            assert server_version is not None and int(server_version) // 10000 == 16, (
                "Replay integration qualification requires PostgreSQL 16"
            )
            # Check the actual connected server endpoint, not only the DSN
            # hostname (which could resolve unexpectedly).
            is_loopback = await connection.scalar(text(
                "SELECT inet_server_addr() << inet '127.0.0.0/8' "
                "OR inet_server_addr() = inet '::1'"
            ))
            assert is_loopback is True, "Replay DB connection must terminate on loopback"
            # Fail rather than creating schema in an unqualified database.
            present = await connection.scalar(
                text("SELECT to_regclass('gateway_assertion_replay')")
            )
            assert present is not None, "Apply reviewed migration 0002 to disposable test DB"
            revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            assert revision == "0002_gateway_replay", (
                "Disposable replay DB must be at reviewed Alembic revision 0002"
            )
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_replay_schema_and_expiry_index_match_migration(replay_db):
    """Inspect the actual PostgreSQL schema, not just migration source."""
    async with replay_db() as session:
        columns = (await session.execute(text(
            "SELECT column_name, data_type, is_nullable, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'gateway_assertion_replay'"
        ))).all()
        indexes = (await session.execute(text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = current_schema() "
            "AND tablename = 'gateway_assertion_replay'"
        ))).all()
    assert {row.column_name: (row.data_type, row.is_nullable, row.character_maximum_length)
            for row in columns} == {
        "assertion_digest": ("character varying", "NO", 64),
        "expires_at": ("timestamp with time zone", "NO", None),
    }
    index_defs = {row.indexname: row.indexdef for row in indexes}
    assert "gateway_assertion_replay_pkey" in index_defs
    assert "ix_gateway_assertion_replay_expires_at" in index_defs
    assert "UNIQUE" in index_defs["gateway_assertion_replay_pkey"].upper()
    assert "expires_at" in index_defs["ix_gateway_assertion_replay_expires_at"]
    assert "UNIQUE" not in index_defs["ix_gateway_assertion_replay_expires_at"].upper()


@pytest.mark.asyncio
async def test_two_concurrent_postgres_sessions_reserve_one_jti(replay_db):
    issuer = "gamma-replay-integration"
    jti = "test-" + uuid4().hex
    expires_at = int(time.time()) + 300
    digest = hashlib.sha256((issuer + "\x00" + jti).encode()).hexdigest()

    async def attempt():
        async with replay_db() as session:
            return await consume_assertion_before_access(
                session, issuer=issuer, assertion_id=jti, expires_at=expires_at
            )

    try:
        # Distinct DB connections compete for the same unique key.
        results = await asyncio.wait_for(
            asyncio.gather(*(attempt() for _ in range(12))), timeout=30
        )
        assert results.count(True) == 1
        assert results.count(False) == 11
        async with replay_db() as session:
            count = await session.scalar(
                text("SELECT count(*) FROM gateway_assertion_replay "
                     "WHERE assertion_digest = :digest"),
                {"digest": digest},
            )
            assert count == 1
    finally:
        # Only delete the exact test row, never truncate shared state.
        async with replay_db() as session:
            await session.execute(
                text("DELETE FROM gateway_assertion_replay "
                     "WHERE assertion_digest = :digest"),
                {"digest": digest},
            )
            await session.commit()


@pytest.mark.asyncio
async def test_committed_postgres_reservation_blocks_later_replay(replay_db):
    issuer = "gamma-replay-integration"
    jti = "test-" + uuid4().hex
    digest = hashlib.sha256((issuer + "\x00" + jti).encode()).hexdigest()
    expires_at = int(time.time()) + 300
    try:
        async with replay_db() as first:
            assert await consume_assertion_before_access(
                first, issuer=issuer, assertion_id=jti, expires_at=expires_at
            )
        async with replay_db() as second:
            assert not await consume_assertion_before_access(
                second, issuer=issuer, assertion_id=jti, expires_at=4102444800
            )
    finally:
        async with replay_db() as session:
            await session.execute(
                text("DELETE FROM gateway_assertion_replay "
                     "WHERE assertion_digest = :digest"),
                {"digest": digest},
            )
            await session.commit()


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://user:pass@localhost/production",
    "postgresql+asyncpg://user:pass@localhost/staging",
    "sqlite+aiosqlite:///tmp/replay_test",
    "postgresql+asyncpg://user:pass@production.internal/gamma_replay_test",
    "postgresql+asyncpg://user:pass@localhost/gamma_replay_test?host=production.internal",
    "postgresql+asyncpg://user:pass@localhost/gamma_replay_test?host=/var/run/postgresql",
    "postgresql+asyncpg://user:pass@localhost/gamma_replay_test?port=5433",
])
def test_refuses_unsafe_test_database_urls(url):
    with pytest.raises(pytest.fail.Exception):
        _require_disposable_database_url(url)


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://user:pass@localhost/gamma_replay_test",
    "postgresql+asyncpg://user:pass@127.0.0.1:5433/gamma_replay_test",
    "postgresql+asyncpg://user:pass@[::1]:55432/gamma_replay_test",
])
def test_accepts_explicit_disposable_test_database_url(url):
    assert _require_disposable_database_url(url) == url

@pytest.mark.asyncio
async def test_postgres_rollback_releases_uncommitted_reservation(replay_db):
    """A reservation that was not committed must not consume a JTI."""
    issuer = "gamma-replay-integration"
    jti = "test-" + uuid4().hex
    digest = hashlib.sha256((issuer + "\x00" + jti).encode()).hexdigest()
    expires_at = int(time.time()) + 300
    try:
        async with replay_db() as first:
            from app.gateway_replay import reserve_assertion_once

            assert await reserve_assertion_once(
                first, issuer=issuer, assertion_id=jti, expires_at=expires_at,
            )
            await first.rollback()
        async with replay_db() as second:
            assert await consume_assertion_before_access(
                second, issuer=issuer, assertion_id=jti, expires_at=expires_at,
            )
        async with replay_db() as verifier:
            assert await verifier.scalar(
                text("SELECT count(*) FROM gateway_assertion_replay "
                     "WHERE assertion_digest = :digest"),
                {"digest": digest},
            ) == 1
    finally:
        async with replay_db() as cleanup:
            await cleanup.execute(
                text("DELETE FROM gateway_assertion_replay "
                     "WHERE assertion_digest = :digest"),
                {"digest": digest},
            )
            await cleanup.commit()


@pytest.mark.asyncio
async def test_postgres_same_jti_is_independent_across_issuers(replay_db):
    """Issuer is part of the unique replay key, not only the assertion ID."""
    jti = "test-" + uuid4().hex
    issuers = ("gamma-replay-issuer-a", "gamma-replay-issuer-b")
    expires_at = int(time.time()) + 300
    digests = [
        hashlib.sha256((issuer + "\x00" + jti).encode()).hexdigest()
        for issuer in issuers
    ]
    try:
        for issuer in issuers:
            async with replay_db() as session:
                assert await consume_assertion_before_access(
                    session, issuer=issuer, assertion_id=jti,
                    expires_at=expires_at,
                )
        for issuer in issuers:
            async with replay_db() as session:
                assert not await consume_assertion_before_access(
                    session, issuer=issuer, assertion_id=jti,
                    expires_at=expires_at,
                )
    finally:
        async with replay_db() as cleanup:
            await cleanup.execute(
                text("DELETE FROM gateway_assertion_replay "
                     "WHERE assertion_digest IN (:first, :second)"),
                {"first": digests[0], "second": digests[1]},
            )
            await cleanup.commit()

@pytest.mark.asyncio
async def test_postgres_competing_insert_waits_for_rollback_then_succeeds(replay_db):
    """Exercise real unique-index contention, not only sequential rollback."""
    from app.gateway_replay import reserve_assertion_once

    issuer = "gamma-replay-integration"
    jti = "test-" + uuid4().hex
    expires_at = int(time.time()) + 300
    digest = hashlib.sha256((issuer + "\x00" + jti).encode()).hexdigest()
    started = asyncio.Event()

    async def competing_attempt():
        async with replay_db() as second:
            # Ensure the contender owns a real DB connection before signalling.
            # Signalling before session checkout could make the wait assertion
            # pass solely because the pool has not scheduled the contender.
            await second.connection()
            started.set()
            return await consume_assertion_before_access(
                second, issuer=issuer, assertion_id=jti,
                expires_at=expires_at,
            )

    task = None
    try:
        async with replay_db() as first:
            assert await reserve_assertion_once(
                first, issuer=issuer, assertion_id=jti,
                expires_at=expires_at,
            )
            task = asyncio.create_task(competing_attempt())
            await asyncio.wait_for(started.wait(), timeout=5)
            # The competing INSERT cannot commit the same unique key while
            # the first reservation is still uncommitted.
            await asyncio.sleep(0.1)
            assert not task.done()
            await first.rollback()
        assert await asyncio.wait_for(task, timeout=15) is True
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with replay_db() as cleanup:
            await cleanup.execute(
                text("DELETE FROM gateway_assertion_replay "
                     "WHERE assertion_digest = :digest"),
                {"digest": digest},
            )
            await cleanup.commit()

@pytest.mark.asyncio
async def test_postgres_competing_insert_after_commit_is_rejected(replay_db):
    """A waiting contender must lose once the first transaction commits."""
    from app.gateway_replay import reserve_assertion_once

    issuer = "gamma-replay-integration"
    jti = "test-" + uuid4().hex
    expires_at = int(time.time()) + 300
    digest = hashlib.sha256((issuer + "\x00" + jti).encode()).hexdigest()
    started = asyncio.Event()

    async def competing_attempt():
        async with replay_db() as second:
            # Ensure the contender owns a real DB connection before signalling.
            # Signalling before session checkout could make the wait assertion
            # pass solely because the pool has not scheduled the contender.
            await second.connection()
            started.set()
            return await consume_assertion_before_access(
                second, issuer=issuer, assertion_id=jti,
                expires_at=expires_at,
            )

    task = None
    try:
        async with replay_db() as first:
            assert await reserve_assertion_once(
                first, issuer=issuer, assertion_id=jti,
                expires_at=expires_at,
            )
            task = asyncio.create_task(competing_attempt())
            await asyncio.wait_for(started.wait(), timeout=5)
            await asyncio.sleep(0.1)
            assert not task.done()
            await first.commit()
        assert await asyncio.wait_for(task, timeout=15) is False
        async with replay_db() as verifier:
            assert await verifier.scalar(
                text("SELECT count(*) FROM gateway_assertion_replay "
                     "WHERE assertion_digest = :digest"),
                {"digest": digest},
            ) == 1
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with replay_db() as cleanup:
            await cleanup.execute(
                text("DELETE FROM gateway_assertion_replay "
                     "WHERE assertion_digest = :digest"),
                {"digest": digest},
            )
            await cleanup.commit()
