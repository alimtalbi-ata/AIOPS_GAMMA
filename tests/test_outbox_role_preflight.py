"""Read-only privilege qualification against disposable PostgreSQL."""
import os
import asyncpg
import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("dsn_var", ["GAMMA_WORKER_A_DSN", "GAMMA_WORKER_B_DSN"])
async def test_worker_privilege_preflight(dsn_var):
    if os.getenv("GAMMA_TEST_DISPOSABLE") != "1":
        pytest.skip("Disposable database required")
    conn = await asyncpg.connect(os.environ[dsn_var])
    try:
        assert await conn.fetchval("SELECT current_user = session_user")
        unsafe = await conn.fetch("""
            SELECT rolname FROM pg_roles
            WHERE pg_has_role(session_user, oid, 'MEMBER')
              AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)
        """)
        assert not unsafe
        assert await conn.fetchval("SELECT pg_has_role(session_user, 'gamma_outbox_worker', 'MEMBER')")
        assert not await conn.fetchval("SELECT pg_has_role(session_user, 'gamma_app', 'MEMBER')")
        table = await conn.fetchrow("""
            SELECT relrowsecurity, relforcerowsecurity,
                   pg_has_role(session_user, relowner, 'MEMBER') AS owner_member
            FROM pg_class WHERE oid = 'public.integration_outbox'::regclass
        """)
        assert table["relrowsecurity"] and table["relforcerowsecurity"]
        assert not table["owner_member"]
        for privilege in ("INSERT", "DELETE", "TRUNCATE", "TRIGGER", "REFERENCES"):
            assert not await conn.fetchval(
                "SELECT has_table_privilege(session_user, 'public.integration_outbox', $1)", privilege)
        assert not await conn.fetchval("SELECT has_table_privilege(session_user, 'public.integration_outbox', 'UPDATE')")
        for column in ("id", "tenant_id", "payload", "event_type", "aggregate_id"):
            assert not await conn.fetchval(
                "SELECT has_column_privilege(session_user, 'public.integration_outbox', $1, 'UPDATE')", column)
    finally:
        await conn.close()
