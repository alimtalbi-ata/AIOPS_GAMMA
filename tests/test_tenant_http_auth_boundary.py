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
    assert response.status_code == 401


def test_http_service_key_without_tenant_denied(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    with TestClient(app) as client:
        response = client.post(PATH, headers={"X-Internal-API-Key": "lab-secret"})
    assert response.status_code == 401


def test_http_shared_service_key_and_caller_selected_tenant_are_insufficient(monkeypatch):
    """A service key and untrusted tenant header cannot establish tenant access."""
    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    tenant_a, tenant_b = str(uuid4()), str(uuid4())
    with TestClient(app) as client:
        responses = [client.post(PATH, headers={
            "X-Internal-API-Key": "lab-secret", "X-Tenant-ID": tenant
        }) for tenant in (tenant_a, tenant_b)]
    assert all(response.status_code == 401 for response in responses)



def test_http_wrong_service_key_denied_even_with_valid_tenant(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    with TestClient(app) as client:
        response = client.post(PATH, headers={
            "X-Internal-API-Key": "wrong-key", "X-Tenant-ID": str(uuid4())
        })
    assert response.status_code == 401


def test_http_nil_tenant_denied(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    with TestClient(app) as client:
        response = client.post(PATH, headers={
            "X-Internal-API-Key": "lab-secret",
            "X-Tenant-ID": "00000000-0000-0000-0000-000000000000",
        })
    assert response.status_code == 401


def test_http_forged_actor_headers_must_not_grant_principal(monkeypatch):
    """Unsigned actor/role headers must never establish a verified principal."""
    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    with TestClient(app) as client:
        response = client.post(PATH, headers={
            "X-Internal-API-Key": "lab-secret",
            "X-Tenant-ID": str(uuid4()),
            "X-Actor-ID": "admin",
            "X-Actor-Role": "superadmin",
            "X-Authenticated-User": "admin",
        })
    assert response.status_code == 401
