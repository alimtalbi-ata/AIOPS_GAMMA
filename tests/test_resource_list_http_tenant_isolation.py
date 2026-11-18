"""HTTP tenant isolation on the real resource routes with an in-memory SQL spy.

This checks signed Gateway context and the actual SQLAlchemy WHERE predicates
without a database. It is NOT PostgreSQL, IdP, RLS or upstream ACL qualification.
"""
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.models import Evidence, ServiceBinding
from app.settings import settings


TENANT_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
TENANT_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
INCIDENT = "incident-shared-id"
OTHER_INCIDENT = "incident-other-id"


def signed_headers(path, tenant, *, claimed_tenant=None, grant_incident=True, grant_business=True):
    now = int(time.time())
    claims = {
        "iss": "trusted-gateway", "aud": "gamma-api", "sub": f"user:tenant-isolation-test:{tenant}",
        "actor_type": "user", "tenant_id": str(tenant), "tenant_access": True,
        "iat": now, "exp": now + 30, "jti": "isolation-test-" + uuid4().hex,
        "method": "GET", "path": path,
        "business_permissions": (["bindings:read"] if path.endswith("/bindings") else ["evidence:read"]) if grant_business else [],
        "evidence_incident_grants": [INCIDENT] if grant_incident and path == f"/api/v1/incidents/{INCIDENT}/evidence" else [],
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(
        hmac.new(b"s" * 48, encoded.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": encoded + "." + signature,
        "X-Tenant-ID": str(claimed_tenant or TENANT_B),
        "X-Actor-ID": "forged-admin",
    }


@pytest.fixture(autouse=True)
def gateway_config(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "service-secret")
    monkeypatch.setattr(settings, "gateway_assertion_secret", "s" * 48)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "trusted-gateway")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-api")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class TenantScopedSession:
    """Spy verifies both WHERE columns and applies their bound values to rows."""

    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    async def scalars(self, statement):
        self.queries.append(statement)
        assert statement._limit_clause is not None
        assert int(statement._limit_clause.value) == 500
        where = statement.whereclause
        assert where is not None
        clauses = list(where.clauses) if hasattr(where, "clauses") else [where]
        filters = {}
        for clause in clauses:
            assert clause.operator.__name__ == "eq"
            assert hasattr(clause.left, "key")
            assert hasattr(clause.right, "value")
            filters[clause.left.key] = clause.right.value
        assert filters["tenant_id"] in (TENANT_A, TENANT_B)
        model = statement.column_descriptions[0]["entity"]
        if model is Evidence:
            assert filters["incident_id"] == INCIDENT
        else:
            assert model is ServiceBinding
            assert "incident_id" not in filters
        return Result([
            row for row in self.rows
            if all(getattr(row, key) == value for key, value in filters.items())
        ])


@pytest.mark.parametrize("resource", ["bindings", "evidence"])
def test_real_http_list_routes_isolate_tenants_and_ignore_forged_headers(resource, monkeypatch, replay_unit):
    if resource == "bindings":
        def row(tenant, name):
            return ServiceBinding(
                id=uuid4(), tenant_id=tenant, cmdb_service_id=uuid4(),
                otel_service_name=name, environment="production",
            )
        rows = [row(TENANT_A, "alpha"), row(TENANT_B, "bravo")]
        path = "/api/v1/topology/bindings"
        name_key = "otel_service_name"
    else:
        def row(tenant, incident, name):
            return Evidence(
                id=uuid4(), tenant_id=tenant, incident_id=incident,
                investigation_id=uuid4(), source_type="logs", source_ref=name,
                summary=None, observed_at=datetime.now(timezone.utc),
            )
        rows = [
            row(TENANT_A, INCIDENT, "alpha"),
            row(TENANT_B, INCIDENT, "bravo"),
            row(TENANT_A, OTHER_INCIDENT, "other-incident"),
        ]
        path = f"/api/v1/incidents/{INCIDENT}/evidence"
        name_key = "source_ref"

    session = TenantScopedSession(rows)

    bound_tenants = []

    async def fake_tenant_session(tenant_id):
        bound_tenants.append(tenant_id)
        yield session

    monkeypatch.setattr(main_module, "get_tenant_session", fake_tenant_session)
    with TestClient(app) as client:
        a = client.get(path, headers=signed_headers(path, TENANT_A, claimed_tenant=TENANT_B))
        b = client.get(path, headers=signed_headers(path, TENANT_B, claimed_tenant=TENANT_A))
        denied_business = client.get(path, headers=signed_headers(path, TENANT_A, grant_business=False))
        assert denied_business.status_code == 403, denied_business.text
        if resource == "evidence":
            denied = client.get(path, headers=signed_headers(path, TENANT_A, grant_incident=False))
            assert denied.status_code == 403, denied.text
    assert bound_tenants[:2] == [TENANT_A, TENANT_B]

    assert a.status_code == 200, a.text
    assert b.status_code == 200, b.text
    assert [item[name_key] for item in a.json()] == ["alpha"]
    assert [item[name_key] for item in b.json()] == ["bravo"]
    assert a.headers["Cache-Control"] == "no-store"
    assert b.headers["Cache-Control"] == "no-store"
    assert len(session.queries) == 2
