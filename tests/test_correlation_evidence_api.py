"""Authenticated correlation-evidence API contract tests (dependency override)."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi.testclient import TestClient
from app.main import app
from app.security import Principal, internal_principal

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")


def body(tenant=TENANT):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "correlation": {"signals": [{
            "source": "otel", "external_event_id": "evt-1",
            "service_name": "checkout", "environment": "prod",
            "severity": "major", "status": "firing",
            "observed_at": now, "symptom_key": "latency",
        }]},
        "evidence": [{
            "tenant_id": str(tenant), "incident_id": "inc-1",
            "source": "otel", "external_id": "evt-1",
            "claim": "latency", "observed_at": now,
            "payload": {"latency_ms": 800},
        }],
    }


def test_correlation_evidence_http_preview():
    app.dependency_overrides[internal_principal] = lambda: Principal(TENANT)
    try:
        with TestClient(app) as client:
            result = client.post("/api/v1/incidents/correlation-evidence/preview", json=body())
        assert result.status_code == 200, result.text
        assert result.headers["cache-control"] == "no-store"
        assert result.json()["groups"][0]["evidence_state"] == "UNVERIFIED"
        assert result.json()["persisted"] is False
        assert result.json()["live_remediation_authorized"] is False
    finally:
        app.dependency_overrides.clear()


def test_correlation_evidence_http_cross_tenant():
    app.dependency_overrides[internal_principal] = lambda: Principal(TENANT)
    try:
        with TestClient(app) as client:
            result = client.post("/api/v1/incidents/correlation-evidence/preview", json=body(OTHER))
        assert result.status_code == 403
    finally:
        app.dependency_overrides.clear()
