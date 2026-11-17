"""Negative HTTP auth cases for tenant-owned list endpoints.

Tests the real FastAPI app and proves rejection happens before the database
dependency is entered. No real PostgreSQL, IdP, or resource ACL qualification.
"""
import base64
import hashlib
import hmac
import json
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.settings import settings


PATHS = (
    "/api/v1/topology/bindings",
    "/api/v1/incidents/shared-incident/evidence",
)


@pytest.fixture(autouse=True)
def configure_gateway(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "service-secret")
    monkeypatch.setattr(settings, "gateway_assertion_secret", "s" * 48)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "trusted-gateway")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-api")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)


def signed(path, *, access=True, tenant=None, method="GET"):
    now = int(time.time())
    claims = {
        "iss": "trusted-gateway", "aud": "gamma-api", "sub": "user:123",
        "actor_type": "user", "tenant_id": tenant or str(uuid4()),
        "tenant_access": access, "iat": now, "exp": now + 30,
        "jti": "negative-http-" + uuid4().hex,
        "method": method, "path": path,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(
        hmac.new(b"s" * 48, encoded.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return encoded + "." + sig


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("case", (
    "missing_key",
    "key_only_with_forged_tenant",
    "wrong_key_with_valid_assertion",
    "false_tenant_access",
    "wrong_path",
    "wrong_method",
    "nil_tenant",
))
def test_rejected_list_request_never_enters_db(path, case):
    called = []

    async def forbidden_session():
        called.append(True)
        raise AssertionError("database dependency entered for rejected principal")
        yield  # pragma: no cover

    app.dependency_overrides[get_session] = forbidden_session
    try:
        headers = {
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": signed(path),
        }
        if case == "missing_key":
            del headers["X-Internal-API-Key"]
        elif case == "key_only_with_forged_tenant":
            del headers["X-Gateway-Principal"]
            headers.update({
                "X-Tenant-ID": str(uuid4()),
                "X-Actor-ID": "superadmin",
                "X-Actor-Role": "superadmin",
            })
        elif case == "wrong_key_with_valid_assertion":
            headers["X-Internal-API-Key"] = "wrong-key"
        elif case == "false_tenant_access":
            headers["X-Gateway-Principal"] = signed(path, access=False)
        elif case == "wrong_path":
            headers["X-Gateway-Principal"] = signed("/api/v1/other")
        elif case == "wrong_method":
            headers["X-Gateway-Principal"] = signed(path, method="POST")
        elif case == "nil_tenant":
            headers["X-Gateway-Principal"] = signed(
                path, tenant="00000000-0000-0000-0000-000000000000"
            )

        with TestClient(app) as client:
            response = client.get(path, headers=headers)
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 401, (case, path, response.text)
    assert response.headers["Cache-Control"] == "no-store"
    assert not called
