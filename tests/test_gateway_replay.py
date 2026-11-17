"""Unit and opt-in PostgreSQL concurrency tests for gateway JTI replay protection."""
import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway_replay import (\n    consume_assertion_before_access, reserve_assertion_once,\n    purge_expired_assertions,\n)


class _Result:
    def __init__(self, value):
        self.value = value

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
    session.execute = async_execute = _cleanup_execute(session, rowcount=17)
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
