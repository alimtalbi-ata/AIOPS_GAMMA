"""Unit and opt-in PostgreSQL concurrency tests for gateway JTI replay protection."""
import asyncio
import os

import pytest
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway_replay import (
    consume_assertion_before_access, reserve_assertion_once,
    purge_expired_assertions,
)


class _Result:
    def __init__(self, value=None, rowcount=0):
        self.value = value
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, result=None, fail_commit=False):
        self.result = result
        self.fail_commit = fail_commit
        self.commits = 0
        self.rollbacks = 0
        self.statement = None

    async def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return _Result(self.result)

    async def commit(self):
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError("commit failed")

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_reserve_uses_unique_insert_and_returns_true_for_new_jti():
    session = _Session("digest")
    assert await reserve_assertion_once(
        session, issuer="gateway", assertion_id="assertion-123", expires_at=2_000_000_000
    ) is True
    assert "ON CONFLICT (assertion_digest) DO NOTHING" in session.statement
    assert session.params["digest"]
    assert session.params["expires_at"] is not None


@pytest.mark.asyncio
async def test_reserve_returns_false_for_duplicate_jti():
    session = _Session(None)
    assert await reserve_assertion_once(
        session, issuer="gateway", assertion_id="assertion-123", expires_at=2_000_000_000
    ) is False


@pytest.mark.asyncio
async def test_consume_commits_new_reservation_before_return():
    session = _Session("digest")
    assert await consume_assertion_before_access(
        session, issuer="gateway", assertion_id="assertion-123", expires_at=2_000_000_000
    ) is True
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_consume_rolls_back_duplicate_once():
    session = _Session(None)
    assert await consume_assertion_before_access(
        session, issuer="gateway", assertion_id="assertion-123", expires_at=2_000_000_000
    ) is False
    assert session.commits == 0
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_consume_rolls_back_commit_failure_and_propagates():
    session = _Session("digest", fail_commit=True)
    with pytest.raises(RuntimeError, match="commit failed"):
        await consume_assertion_before_access(
            session, issuer="gateway", assertion_id="assertion-123", expires_at=2_000_000_000
        )
    assert session.commits == 1
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_replay_reservation_is_atomic_across_independent_postgres_sessions():
    database_url = os.getenv("GAMMA_TEST_DATABASE_URL", "")
    if not database_url:
        pytest.skip("GAMMA_TEST_DATABASE_URL not configured; disposable PostgreSQL required")

    engine = create_async_engine(database_url, pool_size=5, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    issuer = "gamma-concurrency-test"
    assertion_id = "parallel-assertion-123456"
    import hashlib
    digest = hashlib.sha256((issuer + "\x00" + assertion_id).encode()).hexdigest()

    try:
        async with engine.begin() as connection:
            exists = await connection.scalar(text(
                "SELECT to_regclass('public.gateway_assertion_replay') IS NOT NULL"
            ))
            if not exists:
                pytest.fail("Apply Alembic migration 0002 to the disposable database first")
            await connection.execute(
                text("DELETE FROM gateway_assertion_replay WHERE assertion_digest=:digest"),
                {"digest": digest},
            )

        async def attempt():
            async with factory() as session:
                return await consume_assertion_before_access(
                    session, issuer=issuer, assertion_id=assertion_id, expires_at=2_000_000_000
                )

        results = await asyncio.gather(*(attempt() for _ in range(5)))
        assert results.count(True) == 1
        assert results.count(False) == 4
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM gateway_assertion_replay WHERE assertion_digest=:digest"),
                {"digest": digest},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_cleanup_deletes_bounded_batch_with_grace_and_commits():
    session = _Session()
    session.execute = _cleanup_execute(session, rowcount=17)
    assert await purge_expired_assertions(session, batch_size=100, grace_seconds=300) == 17
    assert "FOR UPDATE SKIP LOCKED" in session.statement
    assert "NOW()" in session.statement
    assert session.params == {"grace_seconds": 300, "batch_size": 100}
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size,grace", [
    (0, 120), (-1, 120), (10001, 120), (True, 120),
    (10, 0), (10, 59), (10, 86401), (10, True),
])
async def test_cleanup_rejects_unsafe_policy_before_database(batch_size, grace):
    session = _Session()
    with pytest.raises(ValueError, match="invalid replay cleanup policy"):
        await purge_expired_assertions(session, batch_size=batch_size, grace_seconds=grace)
    assert session.commits == 0
    assert session.statement is None


@pytest.mark.asyncio
async def test_cleanup_rolls_back_and_propagates_database_error():
    session = _Session()
    async def fail(statement, params):
        raise RuntimeError("database unavailable")
    session.execute = fail
    with pytest.raises(RuntimeError, match="database unavailable"):
        await purge_expired_assertions(session)
    assert session.rollbacks == 1
    assert session.commits == 0


def _cleanup_execute(session, *, rowcount):
    async def execute(statement, params):
        session.statement = str(statement)
        session.params = params
        return _Result(rowcount=rowcount)
    return execute


@pytest.mark.asyncio
async def test_postgres_cleanup_preserves_live_rows_and_respects_batch_limit():
    database_url = os.getenv("GAMMA_TEST_DATABASE_URL", "")
    if not database_url:
        pytest.skip("GAMMA_TEST_DATABASE_URL not configured; disposable PostgreSQL required")

    import hashlib

    engine = create_async_engine(database_url, pool_size=3, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    prefix = "gamma-cleanup-integration"
    rows = {
        name: hashlib.sha256((prefix + "\x00" + name).encode()).hexdigest()
        for name in ("expired-1", "expired-2", "expired-3", "still-live")
    }
    table_exists = False
    try:
        async with engine.begin() as connection:
            table_exists = await connection.scalar(text(
                "SELECT to_regclass('public.gateway_assertion_replay') IS NOT NULL"
            ))
            if not table_exists:
                pytest.fail("Apply Alembic migration 0002 to the disposable database first")
            await connection.execute(
                text("DELETE FROM gateway_assertion_replay WHERE assertion_digest IN :digests")
                .bindparams(bindparam("digests", expanding=True)),
                {"digests": list(rows.values())},
            )
            await connection.execute(
                text("""
                    INSERT INTO gateway_assertion_replay (assertion_digest, expires_at)
                    VALUES
                    (:e1, NOW() - INTERVAL '10 minutes'),
                    (:e2, NOW() - INTERVAL '9 minutes'),
                    (:e3, NOW() - INTERVAL '8 minutes'),
                    (:live, NOW() + INTERVAL '10 minutes')
                """),
                {"e1": rows["expired-1"], "e2": rows["expired-2"],
                 "e3": rows["expired-3"], "live": rows["still-live"]},
            )

        async with factory() as session:
            deleted = await purge_expired_assertions(session, batch_size=2, grace_seconds=120)
        assert deleted == 2

        async with engine.connect() as connection:
            remaining = set((await connection.execute(
                text("SELECT assertion_digest FROM gateway_assertion_replay WHERE assertion_digest IN :digests")
                .bindparams(bindparam("digests", expanding=True)),
                {"digests": list(rows.values())},
            )).scalars().all())
        assert rows["still-live"] in remaining
        assert len(remaining.intersection({rows["expired-1"], rows["expired-2"], rows["expired-3"]})) == 1

        async with factory() as session:
            deleted_second_batch = await purge_expired_assertions(session, batch_size=2, grace_seconds=120)
        assert deleted_second_batch == 1
        async with engine.connect() as connection:
            live_count = await connection.scalar(
                text("SELECT count(*) FROM gateway_assertion_replay WHERE assertion_digest=:digest"),
                {"digest": rows["still-live"]},
            )
        assert live_count == 1
    finally:
        if table_exists:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM gateway_assertion_replay WHERE assertion_digest IN :digests")
                    .bindparams(bindparam("digests", expanding=True)),
                    {"digests": list(rows.values())},
                )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_two_cleanup_workers_do_not_remove_live_auth_reservation():
    database_url = os.getenv("GAMMA_TEST_DATABASE_URL", "")
    if not database_url:
        pytest.skip("GAMMA_TEST_DATABASE_URL not configured; disposable PostgreSQL required")

    import hashlib

    engine = create_async_engine(database_url, pool_size=6, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    prefix = "gamma-cleanup-workers"
    expired_digests = [
        hashlib.sha256((prefix + "\x00expired-" + str(i)).encode()).hexdigest()
        for i in range(4)
    ]
    issuer = prefix
    assertion_id = "valid-during-cleanup-123456"
    live_digest = hashlib.sha256((issuer + "\x00" + assertion_id).encode()).hexdigest()
    all_digests = expired_digests + [live_digest]
    table_exists = False
    try:
        async with engine.begin() as connection:
            table_exists = await connection.scalar(text(
                "SELECT to_regclass('public.gateway_assertion_replay') IS NOT NULL"
            ))
            if not table_exists:
                pytest.fail("Apply Alembic migration 0002 to the disposable database first")
            await connection.execute(
                text("DELETE FROM gateway_assertion_replay WHERE assertion_digest IN :digests")
                .bindparams(bindparam("digests", expanding=True)),
                {"digests": all_digests},
            )
            await connection.execute(
                text("""
                    INSERT INTO gateway_assertion_replay (assertion_digest, expires_at)
                    VALUES
                    (:d0, NOW() - INTERVAL '10 minutes'),
                    (:d1, NOW() - INTERVAL '9 minutes'),
                    (:d2, NOW() - INTERVAL '8 minutes'),
                    (:d3, NOW() - INTERVAL '7 minutes')
                """),
                {f"d{i}": digest for i, digest in enumerate(expired_digests)},
            )

        async def cleanup_worker():
            async with factory() as session:
                return await purge_expired_assertions(session, batch_size=2, grace_seconds=120)

        async def authenticate_fresh_assertion():
            async with factory() as session:
                return await consume_assertion_before_access(
                    session, issuer=issuer, assertion_id=assertion_id,
                    expires_at=2_000_000_000,
                )

        cleanup_results = await asyncio.gather(cleanup_worker(), cleanup_worker())
        auth_result = await authenticate_fresh_assertion()
        assert sum(cleanup_results) == 4
        assert auth_result is True

        async with engine.connect() as connection:
            live_count = await connection.scalar(
                text("SELECT count(*) FROM gateway_assertion_replay WHERE assertion_digest=:digest"),
                {"digest": live_digest},
            )
        assert live_count == 1
    finally:
        if table_exists:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM gateway_assertion_replay WHERE assertion_digest IN :digests")
                    .bindparams(bindparam("digests", expanding=True)),
                    {"digests": all_digests},
                )
        await engine.dispose()
