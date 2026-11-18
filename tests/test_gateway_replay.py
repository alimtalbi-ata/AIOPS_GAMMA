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



async def _reset_disposable_replay():
    """Fixture-only reset; never use runtime or maintenance credentials."""
    from sqlalchemy.engine import make_url
    url = make_url(os.environ["GAMMA_REPLAY_FIXTURE_DATABASE_URL"])
    assert (url.host, url.database, url.username) == (
        "127.0.0.1", "gamma_rc01_test", "postgres"
    )
    assert os.environ.get("GAMMA_REPLAY_FIXTURE_ALLOW_RESET") == "I_UNDERSTAND_DISPOSABLE_DB"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT current_database()")) == "gamma_rc01_test"
            assert await connection.scalar(text("SELECT current_user")) == "postgres"
            await connection.execute(text("TRUNCATE public.gateway_assertion_replay"))
    finally:
        await engine.dispose()


def _maintenance_engine():
    from sqlalchemy.engine import make_url
    url = make_url(os.environ["GAMMA_REPLAY_MAINTENANCE_DATABASE_URL"])
    assert (url.host, url.database, url.username) == (
        "127.0.0.1", "gamma_rc01_test", "gamma_replay_ci"
    )
    return create_async_engine(url)


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
            await _reset_disposable_replay()

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
            await _reset_disposable_replay()
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
    maintenance = _maintenance_engine()
    maintenance_factory = async_sessionmaker(maintenance, expire_on_commit=False)
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
            await _reset_disposable_replay()
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

        async with maintenance_factory() as session:
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

        async with maintenance_factory() as session:
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
                await _reset_disposable_replay()
        await engine.dispose()
        await maintenance.dispose()


@pytest.mark.asyncio
async def test_two_postgres_cleanup_workers_race_with_fresh_gateway_authentication():
    database_url = os.getenv("GAMMA_TEST_DATABASE_URL", "")
    if not database_url:
        pytest.skip("GAMMA_TEST_DATABASE_URL not configured; disposable PostgreSQL required")

    import hashlib

    engine = create_async_engine(database_url, pool_size=6, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    maintenance = _maintenance_engine()
    maintenance_factory = async_sessionmaker(maintenance, expire_on_commit=False)
    prefix = "gamma-cleanup-auth-race"
    expired = [
        hashlib.sha256((prefix + "\x00expired-" + str(index)).encode()).hexdigest()
        for index in range(4)
    ]
    issuer = prefix
    assertion_id = "fresh-assertion-during-cleanup"
    live_digest = hashlib.sha256((issuer + "\x00" + assertion_id).encode()).hexdigest()
    all_digests = expired + [live_digest]
    table_exists = False

    try:
        async with engine.begin() as connection:
            table_exists = await connection.scalar(text(
                "SELECT to_regclass('public.gateway_assertion_replay') IS NOT NULL"
            ))
            if not table_exists:
                pytest.fail("Apply Alembic migration 0002 to the disposable database first")
            await _reset_disposable_replay()
            await connection.execute(
                text("""
                    INSERT INTO gateway_assertion_replay (assertion_digest, expires_at)
                    VALUES
                    (:d0, NOW() - INTERVAL '10 minutes'),
                    (:d1, NOW() - INTERVAL '9 minutes'),
                    (:d2, NOW() - INTERVAL '8 minutes'),
                    (:d3, NOW() - INTERVAL '7 minutes')
                """),
                {f"d{index}": digest for index, digest in enumerate(expired)},
            )

        async def cleanup_worker():
            async with maintenance_factory() as session:
                return await purge_expired_assertions(
                    session, batch_size=2, grace_seconds=120
                )

        async def authenticate():
            async with factory() as session:
                return await consume_assertion_before_access(
                    session, issuer=issuer, assertion_id=assertion_id,
                    expires_at=2_000_000_000,
                )

        deleted_a, deleted_b, accepted = await asyncio.gather(
            cleanup_worker(), cleanup_worker(), authenticate()
        )
        assert deleted_a + deleted_b == 4
        assert accepted is True

        async with engine.connect() as connection:
            live_count = await connection.scalar(
                text("""
                    SELECT count(*) FROM gateway_assertion_replay
                    WHERE assertion_digest = :digest
                """),
                {"digest": live_digest},
            )
            expired_count = await connection.scalar(
                text("""
                    SELECT count(*) FROM gateway_assertion_replay
                    WHERE assertion_digest IN :digests
                """).bindparams(bindparam("digests", expanding=True)),
                {"digests": expired},
            )
        assert live_count == 1
        assert expired_count == 0
    finally:
        if table_exists:
            async with engine.begin() as connection:
                await _reset_disposable_replay()
        await engine.dispose()
        await maintenance.dispose()
