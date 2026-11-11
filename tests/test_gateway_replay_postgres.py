"""Opt-in REAL PostgreSQL replay concurrency tests.

Run only against an isolated disposable DB with migration 0002 applied:
    GAMMA_REPLAY_TEST_DATABASE_URL=postgresql+asyncpg://... pytest -q tests/test_gateway_replay_postgres.py

Never point this at staging/production; tests write replay reservations.
"""
import asyncio
import hashlib
import os
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
    return raw_url


@pytest_asyncio.fixture
async def replay_db():
    url = _require_disposable_database_url(
        os.environ.get("GAMMA_REPLAY_TEST_DATABASE_URL", "")
    )
    engine = create_async_engine(url, pool_size=4, max_overflow=0)
    try:
        async with engine.connect() as connection:
            # Verify the connected DB identity as well as the URL before writes.
            db_name = await connection.scalar(text("SELECT current_database()"))
            assert db_name and db_name.endswith("_replay_test"), "Unsafe database identity"
            # Fail rather than creating schema in an unqualified database.
            present = await connection.scalar(
                text("SELECT to_regclass('gateway_assertion_replay')")
            )
            assert present is not None, "Apply reviewed migration 0002 to disposable test DB"
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_two_concurrent_postgres_sessions_reserve_one_jti(replay_db):
    issuer = "gamma-replay-integration"
    jti = "test-" + uuid4().hex
    expires_at = 4102444800
    digest = hashlib.sha256((issuer + "\x00" + jti).encode()).hexdigest()

    async def attempt():
        async with replay_db() as session:
            return await consume_assertion_before_access(
                session, issuer=issuer, assertion_id=jti, expires_at=expires_at
            )

    try:
        # Distinct DB connections compete for the same unique key.
        results = await asyncio.wait_for(
            asyncio.gather(attempt(), attempt()), timeout=15
        )
        assert sorted(results) == [False, True]
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
    try:
        async with replay_db() as first:
            assert await consume_assertion_before_access(
                first, issuer=issuer, assertion_id=jti, expires_at=4102444800
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
])
def test_refuses_unsafe_test_database_urls(url):
    with pytest.raises(pytest.fail.Exception):
        _require_disposable_database_url(url)


def test_accepts_explicit_disposable_test_database_url():
    url = "postgresql+asyncpg://user:pass@localhost/gamma_replay_test"
    assert _require_disposable_database_url(url) == url
