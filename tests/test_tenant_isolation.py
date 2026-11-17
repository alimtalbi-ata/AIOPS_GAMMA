"""Tenant scoping regression tests for persistence route boundaries."""
from datetime import datetime, timezone
from uuid import uuid4

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
    compiled = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "telemetry_service_bindings.tenant_id" in compiled
    assert str(tenant_a) in compiled


@pytest.mark.asyncio
async def test_evidence_read_query_scopes_both_tenant_and_granted_incident():
    tenant_a = uuid4()
    session = FakeSession()
    await list_evidence("INC-42", principal(tenant_a), session)
    compiled = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "investigation_evidence.tenant_id" in compiled
    assert "investigation_evidence.incident_id" in compiled
    assert str(tenant_a) in compiled
    assert "INC-42" in compiled


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
