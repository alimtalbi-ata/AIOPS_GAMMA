"""HTTP regression for the real GAMMA canonical snapshot route.

This exercises FastAPI's gateway dependency and hard HOLD, not an external IdP,
PostgreSQL resource ACL, or a live Core/Evidence/Twin upstream.
"""
import base64
import hashlib
import hmac
import json
import time
from uuid import uuid4

from unittest.mock import MagicMock, AsyncMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


@pytest.fixture(autouse=True)
def gateway_settings(monkeypatch):
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=object())
    context.__aexit__ = AsyncMock(return_value=False)
    seen = set()
    async def reserve(session, *, issuer, assertion_id, expires_at):
        key = (issuer, assertion_id)
        if key in seen:
            return False
        seen.add(key)
        return True
    monkeypatch.setattr("app.security.get_session_factory", lambda: lambda: context)
    monkeypatch.setattr("app.security.consume_assertion_before_access", reserve)
    monkeypatch.setattr(settings, "gateway_assertion_keys", {})
    monkeypatch.setattr(settings, "internal_api_key", "service-secret")
    monkeypatch.setattr(settings, "gateway_assertion_secret", "s" * 48)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "trusted-gateway")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-api")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)
    monkeypatch.setattr(settings, "enable_canonical_reads", True)
    monkeypatch.setattr(settings, "canonical_read_token", "unqualified-service-token")
    for field in ("core_read_url", "evidence_read_url", "twin_read_url"):
        monkeypatch.setattr(settings, field, "https://upstream.example.test")


def signed_headers(path, *, tenant_id=None, tenant_access=True):
    now = int(time.time())
    claims = {
        "iss": "trusted-gateway", "aud": "gamma-api",
        "sub": "user:123", "actor_type": "user",
        "tenant_id": str(tenant_id or uuid4()),
        "tenant_access": tenant_access, "iat": now, "exp": now + 30,
        "jti": uuid4().hex, "method": "GET", "path": path,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(
        hmac.new(b"s" * 48, encoded.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": encoded + "." + signature,
    }


@pytest.mark.parametrize("resource", ["core", "evidence", "twin"])
def test_signed_gateway_cannot_enable_unqualified_canonical_read(monkeypatch, resource):
    path = f"/api/v1/canonical/{resource}/snapshot"
    def forbidden(*args, **kwargs):
        raise AssertionError("unqualified canonical upstream network request")
    monkeypatch.setattr("app.reused.upstream.httpx.AsyncClient", forbidden)
    with TestClient(app) as client:
        response = client.get(path, headers=signed_headers(path))
    assert response.status_code == 503
    assert response.json()["detail"] == "Canonical actor/tenant/resource ACL not qualified"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("resource", ["core", "evidence", "twin"])
def test_unsigned_or_unattested_gateway_cannot_reach_canonical_read(resource):
    path = f"/api/v1/canonical/{resource}/snapshot"
    with TestClient(app) as client:
        key_only = client.get(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Tenant-Id": str(uuid4()),
            "X-Actor-Id": "admin",
        })
        denied = client.get(path, headers=signed_headers(path, tenant_access=False))
    assert key_only.status_code == 401
    assert denied.status_code == 401
    assert key_only.headers["Cache-Control"] == "no-store"
    assert denied.headers["Cache-Control"] == "no-store"


def test_signed_gateway_unknown_canonical_resource_is_404():
    path = "/api/v1/canonical/not-a-resource/snapshot"
    with TestClient(app) as client:
        response = client.get(path, headers=signed_headers(path))
    assert response.status_code == 404
    assert response.headers["Cache-Control"] == "no-store"
