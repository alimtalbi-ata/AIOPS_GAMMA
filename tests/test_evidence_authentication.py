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


def valid_correlation_evidence_body():
    evidence = valid_evidence_body()["items"][0]
    return {
        "correlation": {"signals": [{
            "source": evidence["source"],
            "external_event_id": evidence["external_id"],
            "service_name": "checkout",
            "environment": "prod",
            "severity": "major",
            "status": "firing",
            "observed_at": evidence["observed_at"],
            "symptom_key": "latency",
        }]},
        "evidence": [evidence],
    }


def test_http_correlation_evidence_complete_and_consistent(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    with TestClient(app) as client:
        response = client.post(
            PATHS[1], json=valid_correlation_evidence_body(),
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is True
    assert result["groups"][0]["evidence_state"] == "UNVERIFIED"
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False


def test_http_correlation_evidence_missing_proof_not_complete(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    body = valid_correlation_evidence_body()
    body["evidence"] = []
    with TestClient(app) as client:
        response = client.post(
            PATHS[1], json=body,
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["evidence_join_complete"] is False
    assert result["evidence_join_consistent"] is False
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"


def test_http_correlation_evidence_cross_tenant_denied(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    body = valid_correlation_evidence_body()
    body["evidence"][0]["tenant_id"] = "22222222-2222-4222-8222-222222222222"
    with TestClient(app) as client:
        response = client.post(
            PATHS[1], json=body,
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert response.status_code == 403, response.text


def test_http_correlation_evidence_rejects_missing_auth(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    with TestClient(app) as client:
        response = client.post(
            PATHS[1], json=valid_correlation_evidence_body(),
            headers={"X-Tenant-ID": str(TENANT)},
        )
    assert response.status_code == 401, response.text


def test_http_correlation_evidence_rejects_invalid_tenant_header(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    with TestClient(app) as client:
        response = client.post(
            PATHS[1], json=valid_correlation_evidence_body(),
            headers={"X-Tenant-ID": "invalid-tenant",
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert response.status_code == 400, response.text


def test_http_correlation_evidence_rejects_missing_server_key_configuration(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "")
    with TestClient(app) as client:
        response = client.post(
            PATHS[1], json=valid_correlation_evidence_body(),
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert response.status_code == 503, response.text


def test_http_correlation_preview_disables_caching(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    body = valid_correlation_evidence_body()["correlation"]
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/incidents/correlation/preview",
            json=body,
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["persisted"] is False
    assert response.json()["live_remediation_authorized"] is False


def test_http_correlation_preview_requires_authentication(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    body = valid_correlation_evidence_body()["correlation"]
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/incidents/correlation/preview",
            json=body,
            headers={"X-Tenant-ID": str(TENANT)},
        )
    assert response.status_code == 401, response.text


def test_http_correlation_group_ids_are_tenant_scoped(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    body = valid_correlation_evidence_body()["correlation"]
    tenant_b = "22222222-2222-4222-8222-222222222222"
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/incidents/correlation/preview", json=body,
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
        second = client.post(
            "/api/v1/incidents/correlation/preview", json=body,
            headers={"X-Tenant-ID": tenant_b,
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert first.status_code == second.status_code == 200
    assert first.json()["groups"][0]["group_id"] != second.json()["groups"][0]["group_id"]
    assert first.headers["cache-control"] == "no-store"
    assert second.headers["cache-control"] == "no-store"
    assert first.json()["live_remediation_authorized"] is False
    assert second.json()["live_remediation_authorized"] is False


def test_http_correlation_preview_rejects_empty_ci_id(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    body = valid_correlation_evidence_body()["correlation"]
    body["signals"][0]["ci_id"] = ""
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/incidents/correlation/preview",
            json=body,
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert response.status_code == 422, response.text


def test_http_correlation_evidence_preview_rejects_empty_ci_id(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    body = valid_correlation_evidence_body()
    body["correlation"]["signals"][0]["ci_id"] = ""
    with TestClient(app) as client:
        response = client.post(
            PATHS[1], json=body,
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert response.status_code == 422, response.text


def test_http_correlation_preview_rejects_whitespace_ci_id(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    body = valid_correlation_evidence_body()["correlation"]
    body["signals"][0]["ci_id"] = "  "
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/incidents/correlation/preview",
            json=body,
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert response.status_code == 422, response.text


def test_http_correlation_evidence_preview_rejects_whitespace_ci_id(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    body = valid_correlation_evidence_body()
    body["correlation"]["signals"][0]["ci_id"] = " CI-123 "
    with TestClient(app) as client:
        response = client.post(
            PATHS[1], json=body,
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert response.status_code == 422, response.text


def test_http_correlation_preview_accepts_canonical_ci_id(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret-not-production")
    body = valid_correlation_evidence_body()["correlation"]
    body["signals"][0]["ci_id"] = "CI-123"
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/incidents/correlation/preview",
            json=body,
            headers={"X-Tenant-ID": str(TENANT),
                     "X-Internal-API-Key": "test-secret-not-production"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["groups"][0]["ci_id"] == "CI-123"
    assert response.headers["cache-control"] == "no-store"
