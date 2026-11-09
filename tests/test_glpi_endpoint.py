"""Route-level GLPI authentication and tenant-boundary regression tests."""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.reused import glpi_read
from app.settings import settings


def test_glpi_snapshot_requires_internal_auth(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    with TestClient(app) as client:
        response = client.get("/api/v1/itil4/glpi/incidents/12/snapshot",
                              headers={"X-Tenant-Id": str(uuid4())})
    assert response.status_code == 401


def test_glpi_snapshot_rejects_invalid_tenant(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    with TestClient(app) as client:
        response = client.get("/api/v1/itil4/glpi/incidents/12/snapshot",
                              headers={"X-Internal-Api-Key": "test-secret",
                                       "X-Tenant-Id": "not-a-uuid"})
    assert response.status_code == 400


def test_glpi_snapshot_rejects_cross_tenant_without_upstream(monkeypatch):
    tenant = uuid4()
    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    monkeypatch.setattr(settings, "enable_glpi_reads", True)
    monkeypatch.setattr(settings, "glpi_tenant_id", str(uuid4()))
    with TestClient(app) as client:
        response = client.get("/api/v1/itil4/glpi/incidents/12/snapshot",
                              headers={"X-Internal-Api-Key": "test-secret",
                                       "X-Tenant-Id": str(tenant)})
    assert response.status_code == 403
