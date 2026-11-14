"""Authenticated correlation-evidence API contract tests (dependency override)."""
from datetime import datetime, timezone
import time
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.security import Principal, internal_principal

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
PATH = "/api/v1/incidents/correlation-evidence/preview"


def principal():
    return Principal(TENANT, "test-user", "user", "test-assertion-0001", int(time.time()) + 30)


def body(tenant=TENANT, *, evidence_event_id="evt-1", include_evidence=True):
    now = datetime.now(timezone.utc).isoformat()
    result = {
        "correlation": {"signals": [{
            "source": "otel", "external_event_id": "evt-1",
            "service_name": "checkout", "environment": "prod",
            "severity": "major", "status": "firing",
            "observed_at": now, "symptom_key": "latency",
        }]},
        "evidence": [],
    }
    if include_evidence:
        result["evidence"].append({
            "tenant_id": str(tenant), "incident_id": "inc-1",
            "source": "otel", "external_id": evidence_event_id,
            "claim": "latency", "observed_at": now,
            "payload": {"latency_ms": 800},
        })
    return result


def test_correlation_evidence_http_preview_is_unverified_and_no_store():
    app.dependency_overrides[internal_principal] = principal
    try:
        with TestClient(app) as client:
            result = client.post(PATH, json=body())
        assert result.status_code == 200, result.text
        data = result.json()
        assert result.headers["cache-control"] == "no-store"
        assert data["groups"][0]["evidence_state"] == "UNVERIFIED"
        assert data["evidence_join_complete"] is True
        assert data["evidence_join_consistent"] is True
        assert data["persisted"] is False
        assert data["live_remediation_authorized"] is False
    finally:
        app.dependency_overrides.clear()


def test_correlation_evidence_http_cross_tenant_rejected_no_store():
    app.dependency_overrides[internal_principal] = principal
    try:
        with TestClient(app) as client:
            result = client.post(PATH, json=body(OTHER))
        assert result.status_code == 403
        assert result.headers["cache-control"] == "no-store"
    finally:
        app.dependency_overrides.clear()


def test_correlation_evidence_http_missing_evidence_remains_unknown():
    app.dependency_overrides[internal_principal] = principal
    try:
        with TestClient(app) as client:
            result = client.post(PATH, json=body(include_evidence=False))
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["evidence_join_complete"] is False
        assert data["evidence_join_consistent"] is False
        assert data["groups"][0]["evidence_state"] == "UNKNOWN"
        assert data["groups"][0]["evidence_missing_events"] == 1
        assert data["persisted"] is False
        assert data["live_remediation_authorized"] is False
    finally:
        app.dependency_overrides.clear()


def test_correlation_evidence_http_unmatched_evidence_remains_incomplete():
    app.dependency_overrides[internal_principal] = principal
    try:
        with TestClient(app) as client:
            result = client.post(PATH, json=body(evidence_event_id="unrelated-event"))
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["unmatched_evidence"] == 1
        assert data["evidence_join_complete"] is False
        assert data["evidence_join_consistent"] is False
        assert data["groups"][0]["evidence_state"] == "UNKNOWN"
    finally:
        app.dependency_overrides.clear()


def test_correlation_evidence_http_invalid_payload_is_422_no_store():
    app.dependency_overrides[internal_principal] = principal
    try:
        with TestClient(app) as client:
            result = client.post(PATH, json={"correlation": {"signals": []}, "evidence": []})
        assert result.status_code == 422
        assert result.headers["cache-control"] == "no-store"
    finally:
        app.dependency_overrides.clear()
