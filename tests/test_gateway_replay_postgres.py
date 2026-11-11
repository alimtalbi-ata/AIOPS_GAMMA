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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway_replay import consume_assertion_before_access


@pytest.fixture
async def replay_db():
    url = os.environ.get("GAMMA_REPLAY_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("No disposable PostgreSQL test URL configured")
    if not url.startswith("postgresql+asyncpg://"):
        pytest.fail("Replay integration test requires postgresql+asyncpg URL")
    engine = create_async_engine(url, pool_size=4, max_overflow=0)
    try:
        async with engine.connect() as connection:
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
