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


def _token(method, path, grants, tenant_id=None):
    now = int(time.time())
    claims = {
        "iss": "trusted-gateway", "aud": "gamma-api",
        "sub": "user:123", "actor_type": "user",
        "tenant_id": str(tenant_id or uuid4()), "tenant_access": True,
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


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("auth_case", ["missing_assertion", "wrong_service_key", "tampered_assertion"])
def test_evidence_authentication_fail_closed_before_db(client, method, auth_case):
    test_client, calls = client
    path = "/api/v1/incidents/inc-1/evidence"
    token = _token(method, path, ["inc-1"])
    headers = {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": token,
    }
    if auth_case == "missing_assertion":
        headers.pop("X-Gateway-Principal")
    elif auth_case == "wrong_service_key":
        headers["X-Internal-API-Key"] = "wrong-service-key"
    else:
        encoded, signature = token.split(".")
        headers["X-Gateway-Principal"] = encoded + "." + (
            ("A" if signature[0] != "A" else "B") + signature[1:]
        )
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
    assert response.headers["cache-control"] == "no-store"
    assert calls == []


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("bad_grant", ["*", "inc/1", "cafe\u0301", "inc\u0085name"])
def test_invalid_signed_incident_grants_fail_before_db(client, method, bad_grant):
    test_client, calls = client
    path = "/api/v1/incidents/inc-1/evidence"
    headers = {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": _token(method, path, [bad_grant]),
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
    assert response.headers["cache-control"] == "no-store"
    assert calls == []


def test_authorized_evidence_read_filters_by_signed_tenant_and_incident(client):
    """A valid incident grant must not turn the evidence query into a cross-tenant read."""
    from sqlalchemy.dialects import postgresql

    test_client, _ = client
    path = "/api/v1/incidents/inc-1/evidence"
    token = _token("GET", path, ["inc-1"])
    encoded = token.split(".")[0]
    claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    expected_tenant = claims["tenant_id"]
    queries = []

    class EmptyRows:
        def all(self):
            return []

    class InspectingSession:
        async def scalars(self, statement):
            compiled = statement.compile(dialect=postgresql.dialect())
            queries.append((str(compiled), compiled.params))
            return EmptyRows()

    async def inspecting_db():
        yield InspectingSession()

    app.dependency_overrides[get_session] = inspecting_db
    try:
        response = test_client.get(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
            "X-Tenant-ID": str(uuid4()),
        })
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200, response.text
    assert response.json() == []
    assert len(queries) == 1
    sql, params = queries[0]
    assert "tenant_id" in sql and "incident_id" in sql
    assert expected_tenant in {str(value) for value in params.values()}
    assert "inc-1" in params.values()
    assert "tenant_id =" in sql and "incident_id =" in sql
    assert " AND " in sql.upper()
    assert "LIMIT" in sql.upper()
    assert 500 in params.values()


def test_authorized_evidence_write_uses_signed_tenant_and_exact_incident(client):
    """An unsigned tenant header cannot change the persisted evidence owner."""
    test_client, _ = client
    path = "/api/v1/incidents/inc-1/evidence"
    token = _token("POST", path, ["inc-1"])
    encoded = token.split(".")[0]
    claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    captured = []
    commits = []

    class RecordingSession:
        def add(self, obj):
            captured.append(obj)

        async def commit(self):
            commits.append(True)

    async def recording_db():
        yield RecordingSession()

    app.dependency_overrides[get_session] = recording_db
    try:
        response = test_client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
            "X-Tenant-ID": str(uuid4()),
        }, json={
            "investigation_id": str(uuid4()),
            "source_type": "logs",
            "source_ref": "otel:trace-1",
            "summary": "Synthetic evidence",
            "observed_at": "2026-11-15T12:00:00Z",
        })
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 201, response.text
    assert len(captured) == 1 and commits == [True]
    assert str(captured[0].tenant_id) == claims["tenant_id"]
    assert captured[0].incident_id == "inc-1"


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_authorized_evidence_response_is_never_cacheable(client, method):
    """Tenant evidence must not be cached even when the grant is valid."""
    test_client, _ = client
    path = "/api/v1/incidents/inc-1/evidence"
    token = _token(method, path, ["inc-1"])

    class Rows:
        def all(self):
            return []

    class Session:
        async def scalars(self, statement):
            return Rows()

        def add(self, obj):
            pass

        async def commit(self):
            pass

    async def db():
        yield Session()

    app.dependency_overrides[get_session] = db
    try:
        headers = {
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
        }
        if method == "GET":
            response = test_client.get(path, headers=headers)
            assert response.status_code == 200, response.text
        else:
            response = test_client.post(path, headers=headers, json={
                "investigation_id": str(uuid4()),
                "source_type": "logs",
                "source_ref": "otel:trace-1",
                "summary": "Synthetic evidence",
                "observed_at": "2026-11-15T12:00:00Z",
            })
            assert response.status_code == 201, response.text
        assert response.headers["cache-control"] == "no-store"
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_e2e_two_tenants_same_incident_never_cross_read(client):
    """Signed gateway -> FastAPI -> SQLAlchemy scoped query -> response."""
    from sqlalchemy.dialects import postgresql

    test_client, _ = client
    tenant_a, tenant_b = uuid4(), uuid4()
    incident = "shared-incident"
    path = f"/api/v1/incidents/{incident}/evidence"
    evidence = []

    class Rows:
        def __init__(self, items):
            self.items = items

        def all(self):
            return self.items

    class TenantAwareSession:
        def add(self, obj):
            obj.id = uuid4()
            evidence.append(obj)

        async def commit(self):
            return None

        async def scalars(self, statement):
            compiled = statement.compile(dialect=postgresql.dialect())
            params = list(compiled.params.values())
            assert "tenant_id" in str(compiled)
            assert "incident_id" in str(compiled)
            assert " AND " in str(compiled).upper()
            assert 500 in params
            tenant = next(value for value in params if str(value) in {str(tenant_a), str(tenant_b)})
            incident_id = next(value for value in params if value == incident)
            return Rows([item for item in evidence
                         if item.tenant_id == tenant and item.incident_id == incident_id])

    async def fake_db():
        yield TenantAwareSession()

    app.dependency_overrides[get_session] = fake_db
    try:
        for tenant, marker in ((tenant_a, "tenant-a"), (tenant_b, "tenant-b")):
            response = test_client.post(path, headers={
                "X-Internal-API-Key": "service-secret",
                "X-Gateway-Principal": _token("POST", path, [incident], tenant),
            }, json={
                "investigation_id": str(uuid4()),
                "source_type": "logs",
                "source_ref": marker,
                "summary": marker,
                "observed_at": "2026-11-15T12:00:00Z",
            })
            assert response.status_code == 201, response.text
            assert response.headers["cache-control"] == "no-store"

        for tenant, expected in ((tenant_a, "tenant-a"), (tenant_b, "tenant-b")):
            response = test_client.get(path, headers={
                "X-Internal-API-Key": "service-secret",
                "X-Gateway-Principal": _token("GET", path, [incident], tenant),
                "X-Tenant-ID": str(tenant_b if tenant == tenant_a else tenant_a),
            })
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "no-store"
            assert [row["source_ref"] for row in response.json()] == [expected]

        denied = test_client.get(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": _token("GET", path, [], tenant_a),
        })
        assert denied.status_code == 403
        assert denied.headers["cache-control"] == "no-store"
        before = len(evidence)
        rejected_write = test_client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": _token("POST", path, [], tenant_b),
        }, json={
            "investigation_id": str(uuid4()),
            "source_type": "logs",
            "source_ref": "forbidden-cross-tenant",
            "observed_at": "2026-11-15T12:00:00Z",
        })
        assert rejected_write.status_code == 403
        assert rejected_write.headers["cache-control"] == "no-store"
        assert len(evidence) == before
    finally:
        app.dependency_overrides.pop(get_session, None)
