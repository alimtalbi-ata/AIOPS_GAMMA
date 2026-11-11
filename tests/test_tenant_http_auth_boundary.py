"""HTTP boundary tests. A documented xfail is a SECURITY GAP, not approval.

The metrics preview route returns 501 after the current dependency accepts a
principal; this permits an HTTP-level auth check without DB or LIVE reads.
"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


PATH = "/api/v1/observability/metrics/query"


def test_http_missing_service_key_denied(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    tenant = str(uuid4())
    with TestClient(app) as client:
        response = client.post(PATH, headers={"X-Tenant-ID": tenant})
    assert response.status_code == 401


def test_http_invalid_tenant_denied(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    with TestClient(app) as client:
        response = client.post(PATH, headers={
            "X-Internal-API-Key": "lab-secret", "X-Tenant-ID": "not-a-uuid"
        })
    assert response.status_code == 400


def test_http_service_key_without_tenant_denied(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    with TestClient(app) as client:
        response = client.post(PATH, headers={"X-Internal-API-Key": "lab-secret"})
    assert response.status_code == 400


@pytest.mark.xfail(
    strict=True,
    reason="P0.1/P0.2 missing: shared key + caller-selected tenant currently passes auth",
)
def test_http_shared_service_key_must_not_switch_tenant_without_actor_acl(monkeypatch):
    """Desired policy, currently violated. XPASS after a fix demands review."""
    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    tenant_a, tenant_b = str(uuid4()), str(uuid4())
    with TestClient(app) as client:
        responses = [client.post(PATH, headers={
            "X-Internal-API-Key": "lab-secret", "X-Tenant-ID": tenant
        }) for tenant in (tenant_a, tenant_b)]
    # 501 means the request passed the principal dependency and reached the
    # unimplemented metrics handler. Neither tenant may pass on a key alone.
    assert all(response.status_code in (401, 403) for response in responses)
