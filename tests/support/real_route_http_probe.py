"""Isolated real main.py + security.py HTTP probe. Never import from normal suite."""
import base64
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


# This probe runs in a fresh interpreter. Import real application modules
# rather than replacing their schemas or DB module in sys.modules.
import sqlalchemy.ext.asyncio as sa_async


def forbidden_engine(*args, **kwargs):
    raise AssertionError("HTTP isolation probe attempted real DB engine creation")


sa_async.create_async_engine = forbidden_engine

from app.main import app
from app.settings import settings


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "service-secret")
    monkeypatch.setattr(settings, "gateway_assertion_secret", "s" * 48)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "trusted-gateway")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-api")
    monkeypatch.setattr(settings, "gateway_assertion_keys", {})
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)
    import app.security as security
    import app.db as db
    import app.main as main_module

    # Retain real HMAC and replay transaction code. Model only the database
    # execution result, with an independent context for each reservation.
    seen = set()

    async def reserve(statement, params):
        digest = params["digest"]
        result = MagicMock()
        result.scalar_one_or_none.return_value = None if digest in seen else digest
        seen.add(digest)
        return result

    def session_context():
        session = AsyncMock()
        session.execute.side_effect = reserve
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=session)
        context.__aexit__ = AsyncMock(return_value=False)
        return context

    async def forbidden_tenant_session(tenant_id):
        raise AssertionError("HTTP isolation probe accessed tenant DB")
        yield  # Keep the async generator dependency shape.

    monkeypatch.setattr(security, "get_session_factory", lambda: session_context)
    monkeypatch.setattr(db, "get_session_factory", forbidden_engine)
    monkeypatch.setattr(main_module, "get_tenant_session", forbidden_tenant_session)


PUBLIC = {"/api/v1/health/live", "/api/v1/demo/correlation", "/api/v1/demo/investigation"}
PROTECTED = [
    (next(iter(route.methods)), route.path)
    for route in app.routes
    if route.path.startswith("/api/v1/") and route.path not in PUBLIC
]
EXPECTED_PROTECTED = {
    ("POST", "/api/v1/observability/logs/search"),
    ("POST", "/api/v1/observability/metrics/query"),
    ("POST", "/api/v1/integrations/opensearch/alerts"),
    ("POST", "/api/v1/topology/bindings"),
    ("GET", "/api/v1/topology/bindings"),
    ("POST", "/api/v1/incidents/{incident_id}/evidence"),
    ("GET", "/api/v1/incidents/{incident_id}/evidence"),
    ("POST", "/api/v1/topology/impact/estimate"),
    ("POST", "/api/v1/policy/remediation/preview"),
    ("POST", "/api/v1/incidents/correlation/preview"),
    ("GET", "/api/v1/canonical/{resource}/snapshot"),
    ("POST", "/api/v1/itil4/workflow/preview"),
    ("POST", "/api/v1/itil4/incidents/sync-preview"),
    ("GET", "/api/v1/itil4/glpi/incidents/{ticket_id}/snapshot"),
    ("POST", "/api/v1/observability/llm/kpis/preview"),
    ("POST", "/api/v1/observability/llm/slo/preview"),
    ("POST", "/api/v1/incidents/investigation/preview"),
    ("POST", "/api/v1/incidents/evidence/preview"),
    ("POST", "/api/v1/incidents/correlation-evidence/preview"),
}
assert set(PROTECTED) == EXPECTED_PROTECTED, "Explicit route inventory review required"


@pytest.mark.parametrize("method,path", PROTECTED)
def test_unsigned_actor_rejected(method, path):
    concrete = (path.replace("{incident_id}", "INC-1")
                    .replace("{resource}", "incidents")
                    .replace("{ticket_id}", "1"))
    with TestClient(app) as client:
        response = client.request(method, concrete, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Tenant-ID": str(uuid4()),
        }, json={})
    assert response.status_code == 401, (method, path, response.text)
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", sorted(PUBLIC))
def test_public_route(path):
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200
    if path != "/api/v1/health/live":
        assert response.headers["cache-control"] == "no-store"


def signed(method, path, *, issued_at=None, expires_at=None):
    now = int(time.time())
    claims = {
        "iss": "trusted-gateway", "aud": "gamma-api", "sub": "user:123",
        "actor_type": "user", "tenant_id": str(uuid4()), "tenant_access": True,
        "iat": now if issued_at is None else issued_at,
        "exp": now + 30 if expires_at is None else expires_at,
        "jti": "probe-" + uuid4().hex,
        "method": method, "path": path,
    }
    raw = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(hmac.new(b"s" * 48, raw, hashlib.sha256).digest()).rstrip(b"=")
    return (raw + b"." + sig).decode()


def headers(path, signed_path=None):
    return {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": signed("POST", signed_path or path),
    }


def test_signed_actor_reaches_metrics_route():
    path = "/api/v1/observability/metrics/query"
    with TestClient(app) as client:
        response = client.post(path, headers=headers(path))
    assert response.status_code == 501
    assert response.headers["cache-control"] == "no-store"


def test_wrong_signed_path_rejected():
    path = "/api/v1/observability/metrics/query"
    with TestClient(app) as client:
        response = client.post(path, headers=headers(path, "/api/v1/other"))
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_cross_tenant_evidence_preview_rejected():
    path = "/api/v1/incidents/evidence/preview"
    with TestClient(app) as client:
        response = client.post(path, headers=headers(path),
                               json={"items": [evidence_item(str(uuid4()))]})
    assert response.status_code == 403, response.text
    assert response.headers["cache-control"] == "no-store"


def test_forged_tenant_header_cannot_override_signed_actor():
    path = "/api/v1/observability/metrics/query"
    forged = headers(path)
    forged["X-Tenant-ID"] = str(uuid4())
    with TestClient(app) as client:
        response = client.post(path, headers=forged)
    assert response.status_code == 501
    assert response.headers["cache-control"] == "no-store"

def test_tampered_signed_actor_rejected():
    path = "/api/v1/observability/metrics/query"
    token = signed("POST", path)
    payload, signature = token.split(".")
    tampered = payload + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": tampered,
        })
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_wrong_signed_method_rejected():
    path = "/api/v1/observability/metrics/query"
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": signed("GET", path),
        })
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_expired_signed_actor_rejected():
    path = "/api/v1/observability/metrics/query"
    now = int(time.time())
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": signed(
                "POST", path, issued_at=now - 30, expires_at=now - 1
            ),
        })
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"

def test_signed_actor_without_service_key_rejected():
    path = "/api/v1/observability/metrics/query"
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Gateway-Principal": signed("POST", path),
        })
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def evidence_item(tenant_id):
    return {
        "tenant_id": tenant_id,
        "incident_id": "INC-123",
        "source": "isolated-probe",
        "external_id": "event-123",
        "claim": "synthetic evidence for HTTP contract verification",
        "observed_at": "2026-11-13T12:00:00+00:00",
        "payload": {"synthetic": True},
        "provenance": {"source": "isolated-probe"},
    }


def test_signed_same_tenant_evidence_preview_uses_real_normalizer():
    from app.security import verify_gateway_assertion

    path = "/api/v1/incidents/evidence/preview"
    token = signed("POST", path)
    principal = verify_gateway_assertion(token, method="POST", path=path)
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
        }, json={"items": [evidence_item(str(principal.tenant_id))]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False
    assert result["items"][0]["integrity"] == "UNVERIFIED"
    assert result["items"][0]["tenant_id"] == str(principal.tenant_id)
    assert response.headers["cache-control"] == "no-store"

def test_evidence_preview_rejects_incomplete_item_before_tenant_logic():
    path = "/api/v1/incidents/evidence/preview"
    with TestClient(app) as client:
        response = client.post(path, headers=headers(path),
                               json={"items": [{"tenant_id": str(uuid4())}]})
    assert response.status_code == 422, response.text
    assert response.headers["cache-control"] == "no-store"


def test_same_tenant_evidence_preview_remains_unverified_with_duplicate():
    from app.security import verify_gateway_assertion

    path = "/api/v1/incidents/evidence/preview"
    token = signed("POST", path)
    tenant = str(verify_gateway_assertion(token, method="POST", path=path).tenant_id)
    item = evidence_item(tenant)
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
        }, json={"items": [item, item]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["duplicates"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["integrity"] == "UNVERIFIED"
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False
    assert response.headers["cache-control"] == "no-store"

def test_mixed_tenant_evidence_batch_rejected_atomically():
    from app.security import verify_gateway_assertion

    path = "/api/v1/incidents/evidence/preview"
    token = signed("POST", path)
    tenant = str(verify_gateway_assertion(token, method="POST", path=path).tenant_id)
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
        }, json={"items": [evidence_item(tenant), evidence_item(str(uuid4()))]})
    assert response.status_code == 403, response.text
    assert response.headers["cache-control"] == "no-store"


def test_evidence_preview_rejects_naive_timestamp():
    from app.security import verify_gateway_assertion

    path = "/api/v1/incidents/evidence/preview"
    token = signed("POST", path)
    tenant = str(verify_gateway_assertion(token, method="POST", path=path).tenant_id)
    item = evidence_item(tenant)
    item["observed_at"] = "2026-11-13T12:00:00"
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
        }, json={"items": [item]})
    assert response.status_code == 422, response.text
    assert response.headers["cache-control"] == "no-store"

def test_conflicting_evidence_versions_never_become_verified():
    from app.security import verify_gateway_assertion

    path = "/api/v1/incidents/evidence/preview"
    token = signed("POST", path)
    tenant = str(verify_gateway_assertion(token, method="POST", path=path).tenant_id)
    first = evidence_item(tenant)
    second = evidence_item(tenant)
    second["payload"] = {"synthetic": False, "conflicting": True}
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
        }, json={"items": [first, second]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["duplicates"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["state"] == "UNKNOWN"
    assert result["items"][0]["integrity"] == "UNVERIFIED"
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False
    assert response.headers["cache-control"] == "no-store"

def test_cross_tenant_batch_does_not_invoke_normalizer(monkeypatch):
    from app.security import verify_gateway_assertion
    import app.main as main_module

    path = "/api/v1/incidents/evidence/preview"
    token = signed("POST", path)
    tenant = str(verify_gateway_assertion(token, method="POST", path=path).tenant_id)
    calls = []
    original = main_module.normalize_evidence

    def tracked_normalize(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(main_module, "normalize_evidence", tracked_normalize)
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
        }, json={"items": [evidence_item(tenant), evidence_item(str(uuid4()))]})
    assert response.status_code == 403, response.text
    assert calls == []
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("resource,expected", [("core", 503), ("evidence", 503), ("twin", 503), ("unlisted", 404)])
def test_canonical_http_hold_without_network(resource, expected, monkeypatch):
    import httpx

    def forbidden_client(*args, **kwargs):
        raise AssertionError("Canonical HOLD must not instantiate an HTTP client")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden_client)
    path = f"/api/v1/canonical/{resource}/snapshot"
    with TestClient(app) as client:
        response = client.get(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": signed("GET", path),
        })
    assert response.status_code == expected, response.text
    assert response.headers["cache-control"] == "no-store"

@pytest.mark.parametrize("resource", ["core", "evidence", "twin"])
def test_canonical_legacy_enable_flag_cannot_bypass_hold(resource, monkeypatch):
    import httpx

    monkeypatch.setattr(settings, "enable_canonical_reads", True)
    monkeypatch.setattr(settings, "canonical_read_token", "unused-test-token")
    monkeypatch.setattr(settings, "core_read_url", "https://core.example.invalid")
    monkeypatch.setattr(settings, "evidence_read_url", "https://evidence.example.invalid")
    monkeypatch.setattr(settings, "twin_read_url", "https://twin.example.invalid")

    def forbidden_client(*args, **kwargs):
        raise AssertionError("Legacy enable flag must not open an upstream connection")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden_client)
    monkeypatch.setattr(httpx, "Client", forbidden_client)
    path = f"/api/v1/canonical/{resource}/snapshot"
    with TestClient(app) as client:
        response = client.get(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": signed("GET", path),
        })
    assert response.status_code == 503, response.text
    assert response.headers["cache-control"] == "no-store"

def test_evidence_preview_rejects_501_items_before_normalization(monkeypatch):
    from app.security import verify_gateway_assertion
    import app.main as main_module

    path = "/api/v1/incidents/evidence/preview"
    token = signed("POST", path)
    tenant = str(verify_gateway_assertion(token, method="POST", path=path).tenant_id)
    calls = []
    monkeypatch.setattr(main_module, "normalize_evidence", lambda *a, **kw: calls.append(1))
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
        }, json={"items": [evidence_item(tenant)] * 501})
    assert response.status_code == 422, response.text
    assert calls == []
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("max_age", [0, 86401])
def test_evidence_preview_rejects_invalid_age_bounds_before_normalization(max_age, monkeypatch):
    from app.security import verify_gateway_assertion
    import app.main as main_module

    path = "/api/v1/incidents/evidence/preview"
    token = signed("POST", path)
    tenant = str(verify_gateway_assertion(token, method="POST", path=path).tenant_id)
    calls = []
    monkeypatch.setattr(main_module, "normalize_evidence", lambda *a, **kw: calls.append(1))
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
        }, json={"items": [evidence_item(tenant)], "max_age_seconds": max_age})
    assert response.status_code == 422, response.text
    assert calls == []
    assert response.headers["cache-control"] == "no-store"

@pytest.mark.parametrize("field,bytes_count", [("payload", 65537), ("provenance", 8193)])
def test_evidence_preview_rejects_oversized_json_fields_before_normalization(field, bytes_count, monkeypatch):
    from app.security import verify_gateway_assertion
    import app.main as main_module

    path = "/api/v1/incidents/evidence/preview"
    token = signed("POST", path)
    tenant = str(verify_gateway_assertion(token, method="POST", path=path).tenant_id)
    item = evidence_item(tenant)
    item[field] = {"text": "x" * bytes_count}
    calls = []
    monkeypatch.setattr(main_module, "normalize_evidence", lambda *a, **kw: calls.append(1))
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
        }, json={"items": [item]})
    assert response.status_code == 422, response.text
    assert calls == []
    assert response.headers["cache-control"] == "no-store"
