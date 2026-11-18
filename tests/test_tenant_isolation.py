"""Tenant scoping regression tests for persistence route boundaries."""
from datetime import datetime, timezone
from uuid import uuid4
import os

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

import pytest

from app.main import add_binding, list_bindings, list_evidence
from app.schemas import BindingIn
from app.security import Principal


def principal(tenant_id):
    return Principal(
        tenant_id=tenant_id, subject="user:tenant-test", actor_type="user",
        assertion_id="tenant-test-assertion", expires_at=2_000_000_000,
        evidence_incident_grants=("INC-42",),
    )


class FakeScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.added = []
        self.commits = 0
        self.statement = None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def scalars(self, statement):
        self.statement = statement
        return FakeScalars(self.rows)


@pytest.mark.asyncio
async def test_binding_write_uses_verified_principal_tenant_not_request_data():
    tenant_a, tenant_b = uuid4(), uuid4()
    session = FakeSession()
    request = BindingIn(
        cmdb_service_id=uuid4(), otel_service_name="checkout-api",
        environment="production",
    )
    await add_binding(request, principal(tenant_a), session)
    assert len(session.added) == 1
    assert session.added[0].tenant_id == tenant_a
    assert session.added[0].tenant_id != tenant_b
    assert session.commits == 1


@pytest.mark.asyncio
async def test_binding_read_query_is_tenant_scoped():
    tenant_a = uuid4()
    session = FakeSession()
    await list_bindings(principal(tenant_a), session)
    compiled = session.statement.compile()
    assert "telemetry_service_bindings.tenant_id" in str(compiled)
    assert tenant_a in compiled.params.values()


@pytest.mark.asyncio
async def test_evidence_read_query_scopes_both_tenant_and_granted_incident():
    tenant_a = uuid4()
    session = FakeSession()
    await list_evidence("INC-42", principal(tenant_a), session)
    compiled = session.statement.compile()
    assert "investigation_evidence.tenant_id" in str(compiled)
    assert "investigation_evidence.incident_id" in str(compiled)
    assert tenant_a in compiled.params.values()
    assert "INC-42" in compiled.params.values()


@pytest.mark.asyncio
async def test_evidence_read_denies_cross_tenant_incident_grant_before_query():
    tenant_b = uuid4()
    session = FakeSession()
    with pytest.raises(Exception) as exc:
        await list_evidence("INC-OTHER", principal(tenant_b), session)
    from fastapi import HTTPException
    assert isinstance(exc.value, HTTPException)
    assert exc.value.status_code == 403
    assert session.statement is None


@pytest.mark.asyncio
async def test_binding_write_does_not_accept_caller_supplied_tenant_field():
    with pytest.raises(Exception):
        BindingIn(
            cmdb_service_id=uuid4(), otel_service_name="checkout-api",
            environment="production", tenant_id=str(uuid4()),
        )


@pytest.mark.asyncio
async def test_postgres_rls_denies_cross_tenant_reads_and_writes():
    database_url = os.getenv("GAMMA_TEST_DATABASE_URL", "")
    if not database_url:
        pytest.skip("GAMMA_TEST_DATABASE_URL must point to restricted gamma_app role")
    engine = create_async_engine(database_url, pool_size=1, max_overflow=0)
    tenant_a, tenant_b = uuid4(), uuid4()
    row_id = uuid4()
    seeded = False
    try:
        async with engine.begin() as connection:
            role = await connection.execute(text("""
                SELECT r.rolsuper, r.rolbypassrls
                FROM pg_roles r WHERE r.rolname = current_user
            """))
            is_superuser, bypasses_rls = role.one()
            assert not is_superuser and not bypasses_rls, (
                "RLS integration tests must use the restricted non-superuser runtime role"
            )
            for table in ("integration_inbox", "integration_outbox",
                          "telemetry_service_bindings", "investigation_evidence"):
                policy_active = await connection.scalar(text(
                    "SELECT relrowsecurity AND relforcerowsecurity "
                    "AND NOT pg_has_role(current_user, relowner, 'MEMBER') "
                    "FROM pg_class WHERE oid = to_regclass(:table)"
                ), {"table": "public." + table})
                assert policy_active is True, table
            await connection.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_a)},
            )
            await connection.execute(text("""
                INSERT INTO telemetry_service_bindings
                    (id, tenant_id, cmdb_service_id, otel_service_name, environment)
                VALUES (:id, :tenant, :cmdb, 'gamma-rls-test', 'test')
            """), {"id": row_id, "tenant": tenant_a, "cmdb": uuid4()})

        seeded = True
        async with engine.begin() as connection:
            assert await connection.scalar(text(
                "SELECT NULLIF(current_setting('app.tenant_id', true), '') IS NULL"
            )) is True
            assert await connection.scalar(text(
                "SELECT count(*) FROM telemetry_service_bindings WHERE id=:id"
            ), {"id": row_id}) == 0

        async with engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_b)},
            )
            visible = await connection.scalar(
                text("SELECT count(*) FROM telemetry_service_bindings WHERE id=:id"),
                {"id": row_id},
            )
            assert visible == 0
            for statement in (
                "UPDATE telemetry_service_bindings SET environment='forged' WHERE id=:id",
                "DELETE FROM telemetry_service_bindings WHERE id=:id",
            ):
                result = await connection.execute(text(statement), {"id": row_id})
                assert result.rowcount == 0
            with pytest.raises(DBAPIError) as denied:
                async with connection.begin_nested():
                    await connection.execute(text("""
                        INSERT INTO telemetry_service_bindings
                            (id, tenant_id, cmdb_service_id, otel_service_name, environment)
                        VALUES (:id, :tenant, :cmdb, 'gamma-rls-forged', 'test')
                    """), {"id": uuid4(), "tenant": tenant_a, "cmdb": uuid4()})
            assert denied.value.orig.sqlstate == '42501'
        async with engine.begin() as connection:
            await connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                                     {"tenant": str(tenant_a)})
            assert await connection.scalar(text(
                "SELECT environment FROM telemetry_service_bindings WHERE id=:id"
            ), {"id": row_id}) == "test"

    finally:
        try:
            if seeded:
                async with engine.begin() as connection:
                    await connection.execute(
                        text("SELECT set_config('app.tenant_id', :tenant, true)"),
                        {"tenant": str(tenant_a)},
                    )
                    await connection.execute(
                        text("DELETE FROM telemetry_service_bindings WHERE id=:id"),
                        {"id": row_id},
                    )
        finally:
            await engine.dispose()
