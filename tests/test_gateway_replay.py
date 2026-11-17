"""Unit and opt-in PostgreSQL concurrency tests for gateway JTI replay protection."""
import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway_replay import consume_assertion_before_access, reserve_assertion_once


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
    digest = hashlib.sha256((issuer + "\\x00" + assertion_id).encode()).hexdigest()

    try:
        async with engine.begin() as connection:
            await connection.execute(text("""
                CREATE TABLE IF NOT EXISTS gateway_assertion_replay (
                    assertion_digest VARCHAR(64) PRIMARY KEY,
                    expires_at TIMESTAMPTZ NOT NULL
                )
            """))
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
