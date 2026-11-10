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
