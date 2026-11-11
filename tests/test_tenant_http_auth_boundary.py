"""HTTP boundary tests. A documented xfail is a SECURITY GAP, not approval.

The metrics preview route returns 501 after the current dependency accepts a
principal; this permits an HTTP-level auth check without DB or LIVE reads.
"""
import base64
import hashlib
import hmac
import json
import time
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


def _signed_http_assertion(monkeypatch, *, tenant_id=None, path=PATH, access=True):
    """Sign a deterministic-shape assertion for the HTTP dependency boundary."""
    monkeypatch.setattr(settings, "gateway_assertion_secret", "g" * 48)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "test-gateway")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-api")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)
    now = int(time.time())
    claims = {
        "iss": "test-gateway", "aud": "gamma-api", "sub": "test-user",
        "actor_type": "user", "tenant_id": tenant_id or str(uuid4()),
        "tenant_access": access, "iat": now, "exp": now + 30,
        "jti": "http-" + uuid4().hex, "method": "POST", "path": path,
    }
    payload = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(
        hmac.new(b"g" * 48, payload.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return payload + "." + signature


def test_http_valid_signed_assertion_reaches_disabled_metrics_preview(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    token = _signed_http_assertion(monkeypatch)
    with TestClient(app) as client:
        response = client.post(PATH, headers={
            "X-Internal-API-Key": "lab-secret", "X-Gateway-Principal": token,
        })
    # 501 proves the auth dependency accepted the signed principal;
    # this endpoint does not read tenant data or require a DB.
    assert response.status_code == 501


@pytest.mark.parametrize("case", ["wrong_path", "access_denied", "tampered_signature"])
def test_http_invalid_gateway_assertion_denied(monkeypatch, case):
    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    token = _signed_http_assertion(
        monkeypatch, path="/api/v1/other" if case == "wrong_path" else PATH,
        access=(case != "access_denied"),
    )
    if case == "tampered_signature":
        token = token[:-1] + ("A" if token[-1] != "A" else "B")
    with TestClient(app) as client:
        response = client.post(PATH, headers={
            "X-Internal-API-Key": "lab-secret", "X-Gateway-Principal": token,
        })
    assert response.status_code == 401
