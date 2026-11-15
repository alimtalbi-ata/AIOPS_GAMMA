"""HTTP regressions: signed incident grants gate persisted evidence before DB access."""
import base64
import hashlib
import hmac
import json
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import get_session
from app.settings import settings


def _token(method, path, grants):
    now = int(time.time())
    claims = {
        "iss": "trusted-gateway", "aud": "gamma-api",
        "sub": "user:123", "actor_type": "user",
        "tenant_id": str(uuid4()), "tenant_access": True,
        "iat": now, "exp": now + 30, "jti": "evidence-acl-test-123456",
        "method": method, "path": path,
        "evidence_incident_grants": grants,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(
        hmac.new(b"s" * 48, encoded.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return encoded + "." + signature


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "service-secret")
    monkeypatch.setattr(settings, "gateway_assertion_secret", "s" * 48)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "trusted-gateway")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-api")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)
    calls = []

    class ForbiddenSession:
        def add(self, *args, **kwargs):
            calls.append("add")
            raise AssertionError("Evidence write must not be reached")

        async def commit(self):
            calls.append("commit")
            raise AssertionError("Evidence commit must not be reached")

        async def scalars(self, *args, **kwargs):
            calls.append("scalars")
            raise AssertionError("Evidence read must not be reached")

    async def forbidden_db():
        yield ForbiddenSession()

    app.dependency_overrides[get_session] = forbidden_db
    try:
        with TestClient(app) as test_client:
            yield test_client, calls
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("grants", [[], ["another-incident"]])
def test_denied_evidence_resource_never_queries_db(client, method, grants):
    test_client, calls = client
    path = "/api/v1/incidents/inc-1/evidence"
    headers = {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": _token(method, path, grants),
    }
    if method == "GET":
        response = test_client.get(path, headers=headers)
    else:
        response = test_client.post(path, headers=headers, json={
            "investigation_id": str(uuid4()),
            "source_type": "logs",
            "source_ref": "otel:trace-1",
            "summary": "Synthetic evidence",
            "observed_at": "2026-11-15T12:00:00Z",
        })
    assert response.status_code == 403, response.text
    assert response.headers["cache-control"] == "no-store"
    assert calls == []


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_matching_signed_incident_grant_reaches_database_boundary(client, method):
    test_client, calls = client
    path = "/api/v1/incidents/inc-1/evidence"
    headers = {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": _token(method, path, ["inc-1"]),
    }
    with pytest.raises(AssertionError, match="Evidence (read|write) must not be reached"):
        if method == "GET":
            test_client.get(path, headers=headers)
        else:
            test_client.post(path, headers=headers, json={
                "investigation_id": str(uuid4()),
                "source_type": "logs",
                "source_ref": "otel:trace-1",
                "summary": "Synthetic evidence",
                "observed_at": "2026-11-15T12:00:00Z",
            })
    assert calls == (["scalars"] if method == "GET" else ["add"])
