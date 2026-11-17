"""API contract tests: tenant isolation and read-only evidence preview."""
from datetime import datetime, timezone
import time
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.security import Principal, internal_principal

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
PATH = "/api/v1/incidents/evidence/preview"


def principal():
    return Principal(TENANT, "test-user", "user", "test-assertion-0001", int(time.time()) + 30)


def payload(tenant=TENANT):
    return {"items": [{
        "tenant_id": str(tenant), "incident_id": "inc-1",
        "source": "otel", "external_id": "evt-1", "claim": "latency",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"latency_ms": 800},
    }]}


def test_preview_tenant_bound_and_no_store():
    app.dependency_overrides[internal_principal] = principal
    try:
        with TestClient(app) as client:
            result = client.post(PATH, json=payload())
        assert result.status_code == 200, result.text
        assert result.headers["cache-control"] == "no-store"
        data = result.json()
        assert data["persisted"] is False
        assert data["live_remediation_authorized"] is False
        assert data["items"][0]["integrity"] == "UNVERIFIED"
    finally:
        app.dependency_overrides.clear()


def test_cross_tenant_rejected_no_store():
    app.dependency_overrides[internal_principal] = principal
    try:
        with TestClient(app) as client:
            result = client.post(PATH, json=payload(OTHER))
        assert result.status_code == 403
        assert result.headers["cache-control"] == "no-store"
    finally:
        app.dependency_overrides.clear()


def test_empty_payload_rejected_no_store():
    app.dependency_overrides[internal_principal] = principal
    try:
        with TestClient(app) as client:
            result = client.post(PATH, json={"items": []})
        assert result.status_code == 422
        assert result.headers["cache-control"] == "no-store"
    finally:
        app.dependency_overrides.clear()
