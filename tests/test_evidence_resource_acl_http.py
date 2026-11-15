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


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_untrusted_tenant_header_does_not_create_missing_incident_grant(client, method):
    """An untrusted tenant header cannot create a missing signed incident grant."""
    test_client, calls = client
    path = "/api/v1/incidents/inc-1/evidence"
    headers = {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": _token(method, path, []),
        "X-Tenant-ID": str(uuid4()),
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
    assert calls == []


@pytest.mark.parametrize("method,signed_method,signed_path", [
    ("GET", "POST", "/api/v1/incidents/inc-1/evidence"),
    ("POST", "GET", "/api/v1/incidents/inc-1/evidence"),
    ("GET", "GET", "/api/v1/incidents/inc-2/evidence"),
    ("POST", "POST", "/api/v1/incidents/inc-2/evidence"),
])
def test_signed_incident_grant_is_bound_to_http_method_and_path(
    client, method, signed_method, signed_path
):
    test_client, calls = client
    path = "/api/v1/incidents/inc-1/evidence"
    headers = {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": _token(signed_method, signed_path, ["inc-1"]),
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
    assert response.status_code == 401, response.text
    assert calls == []


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("incident_id", ["*", "inc\u200bname", "cafe\u0301", "inc\u0085name"])
def test_invalid_incident_id_rejected_before_db_access(client, incident_id, method):
    from urllib.parse import quote

    test_client, calls = client
    path = "/api/v1/incidents/" + quote(incident_id, safe="") + "/evidence"
    headers = {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": _token(method, "/api/v1/incidents/" + incident_id + "/evidence", []),
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
    assert response.status_code == 422, response.text
    assert calls == []


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("header_name", ["X-Internal-API-Key", "X-Gateway-Principal"])
def test_duplicate_security_headers_rejected_before_db(client, method, header_name):
    test_client, calls = client
    path = "/api/v1/incidents/inc-1/evidence"
    token = _token(method, path, ["inc-1"])
    headers = [
        ("X-Internal-API-Key", "service-secret"),
        ("X-Gateway-Principal", token),
    ]
    headers.append((header_name, "attacker-value"))
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
    assert response.status_code == 401, response.text
    assert calls == []


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_nfc_incident_grant_reaches_database_boundary(client, method):
    from urllib.parse import quote

    test_client, calls = client
    incident_id = "caf\u00e9"
    decoded_path = "/api/v1/incidents/" + incident_id + "/evidence"
    encoded_path = "/api/v1/incidents/" + quote(incident_id, safe="") + "/evidence"
    headers = {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": _token(method, decoded_path, [incident_id]),
    }
    with pytest.raises(AssertionError, match="Evidence (read|write) must not be reached"):
        if method == "GET":
            test_client.get(encoded_path, headers=headers)
        else:
            test_client.post(encoded_path, headers=headers, json={
                "investigation_id": str(uuid4()),
                "source_type": "logs",
                "source_ref": "otel:trace-1",
                "summary": "Synthetic evidence",
                "observed_at": "2026-11-15T12:00:00Z",
            })
    assert calls == (["scalars"] if method == "GET" else ["add"])


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_unsigned_incident_grant_header_cannot_authorize_evidence(client, method):
    """Only grants inside the verified gateway assertion are authoritative."""
    test_client, calls = client
    path = "/api/v1/incidents/inc-1/evidence"
    headers = {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": _token(method, path, []),
        "X-Evidence-Incident-Grants": "inc-1",
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
    assert calls == []
