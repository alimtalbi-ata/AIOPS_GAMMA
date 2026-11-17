"""GLPI route regression: service key is not actor authorization; ACL HOLD is enforced."""
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.reused import glpi_read
from app.security import Principal, internal_principal
from app.settings import settings

ROUTE = "/api/v1/itil4/glpi/incidents/12/snapshot"


def test_glpi_snapshot_requires_internal_auth(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    previous = app.dependency_overrides.pop(internal_principal, None)
    try:
        with TestClient(app) as client:
            response = client.get(ROUTE, headers={"X-Tenant-Id": str(uuid4())})
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
    finally:
        if previous is not None:
            app.dependency_overrides[internal_principal] = previous


def test_glpi_snapshot_rejects_unverified_tenant_header(monkeypatch):
    """A service key plus caller-selected tenant is not a gateway assertion."""
    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    previous = app.dependency_overrides.pop(internal_principal, None)
    try:
        with TestClient(app) as client:
            response = client.get(ROUTE, headers={
                "X-Internal-Api-Key": "test-secret",
                "X-Tenant-Id": "not-a-uuid",
            })
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
    finally:
        if previous is not None:
            app.dependency_overrides[internal_principal] = previous


def test_glpi_snapshot_remains_on_acl_hold_with_synthetic_principal(monkeypatch):
    """Even an authenticated route dependency cannot enable unqualified GLPI reads."""
    tenant = uuid4()
    monkeypatch.setattr(settings, "enable_glpi_reads", True)
    monkeypatch.setattr(settings, "glpi_tenant_id", str(tenant))
    monkeypatch.setattr(settings, "glpi_entity_id", "8")
    monkeypatch.setattr(settings, "glpi_read_url", "https://glpi.example.test")
    monkeypatch.setattr(settings, "glpi_session_token", "test-session")
    monkeypatch.setattr(settings, "glpi_app_token", "test-app")

    def no_network(*args, **kwargs):
        raise AssertionError("Unqualified GLPI route must not open an HTTP client")

    monkeypatch.setattr(httpx, "AsyncClient", no_network)
    principal = Principal(
        tenant_id=tenant, subject="synthetic-test-actor", actor_type="user",
        assertion_id="synthetic-test-jti", expires_at=1,
    )
    previous = app.dependency_overrides.get(internal_principal)
    app.dependency_overrides[internal_principal] = lambda: principal
    try:
        with TestClient(app) as client:
            response = client.get(ROUTE)
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
        assert "ACL not qualified" in response.json()["detail"]
    finally:
        if previous is None:
            app.dependency_overrides.pop(internal_principal, None)
        else:
            app.dependency_overrides[internal_principal] = previous
