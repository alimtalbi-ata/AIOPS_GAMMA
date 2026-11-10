"""Authentication contract tests for evidence preview routes.

Uses the actual internal_principal dependency: no bypass or mocked identity.
No database connection should be required by these read-only routes.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi.testclient import TestClient
from app.main import app
from app.settings import settings

TENANT = UUID("11111111-1111-4111-8111-111111111111")
PATHS = (
    "/api/v1/incidents/evidence/preview",
    "/api/v1/incidents/correlation-evidence/preview",
)


def test_missing_internal_key_denied(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    with TestClient(app) as client:
        for path in PATHS:
            result = client.post(path, json={},
                                 headers={"X-Tenant-ID": str(TENANT)})
            assert result.status_code == 401, (path, result.text)


def test_invalid_internal_key_denied(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    with TestClient(app) as client:
        for path in PATHS:
            result = client.post(path, json={},
                                 headers={"X-Tenant-ID": str(TENANT),
                                          "X-Internal-API-Key": "wrong"})
            assert result.status_code == 401, (path, result.text)


def test_missing_server_auth_configuration_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "")
    with TestClient(app) as client:
        for path in PATHS:
            result = client.post(path, json={},
                                 headers={"X-Tenant-ID": str(TENANT),
                                          "X-Internal-API-Key": "anything"})
            assert result.status_code == 503, (path, result.text)


def valid_evidence_body():
    return {"items": [{
        "tenant_id": str(TENANT),
        "incident_id": "inc-1",
        "source": "otel",
        "external_id": "evt-1",
        "claim": "latency",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"latency_ms": 800},
    }]}


def test_valid_key_and_tenant_reaches_evidence_preview(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    with TestClient(app) as client:
        result = client.post(
            PATHS[0], json=valid_evidence_body(),
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["items"][0]["integrity"] == "UNVERIFIED"
    assert result.json()["live_remediation_authorized"] is False


def test_authenticated_cross_tenant_evidence_denied(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    body = valid_evidence_body()
    body["items"][0]["tenant_id"] = "22222222-2222-4222-8222-222222222222"
    with TestClient(app) as client:
        result = client.post(
            PATHS[0], json=body,
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert result.status_code == 403, result.text


def test_valid_key_with_invalid_tenant_header_denied(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    with TestClient(app) as client:
        for path in PATHS:
            result = client.post(
                path, json={},
                headers={"X-Tenant-ID": "not-a-uuid",
                         "X-Internal-API-Key": "test-secret-not-production"},
            )
            assert result.status_code == 400, (path, result.text)
