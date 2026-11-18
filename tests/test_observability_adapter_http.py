"""Exercise HTTP authentication through the actual OpenSearch adapter.

The OpenSearch client is faked at the network boundary. No real DLS or
index-mapping qualification is implied by these tests.
"""
from datetime import datetime, timedelta, timezone
from types import ModuleType
from uuid import UUID
import sys

from fastapi.testclient import TestClient

import app.main as main
from app.settings import settings

KEY = "test-gateway-key"
TENANTS = (
    UUID("11111111-1111-4111-8111-111111111111"),
    UUID("22222222-2222-4222-8222-222222222222"),
)


def signed_headers(monkeypatch, tenant, service="checkout"):
    import base64
    import hashlib
    import hmac
    import json
    import time
    from uuid import uuid4

    secret = "s" * 48
    monkeypatch.setattr(settings, "gateway_assertion_secret", secret)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "test-gateway")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-api")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)
    now = int(time.time())
    claims = {"iss": "test-gateway", "aud": "gamma-api", "sub": "user:logs-test",
              "actor_type": "user", "tenant_id": str(tenant), "tenant_access": True,
              "iat": now, "exp": now + 30, "jti": uuid4().hex,
              "method": "POST", "path": "/api/v1/observability/logs/search",
              "log_service_grants": [service]}
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), encoded, hashlib.sha256).digest()).rstrip(b"=")
    return {"X-Internal-API-Key": KEY, "X-Gateway-Principal": (encoded + b"." + sig).decode()}


def payload(service):
    end = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    return {
        "service_name": service,
        "window": {
            "start": (end - timedelta(minutes=5)).isoformat(),
            "end": end.isoformat(),
        },
        "limit": 4,
    }


def test_http_to_adapter_scopes_each_tenant_and_service(monkeypatch, replay_unit):
    monkeypatch.setattr(settings, "internal_api_key", KEY)
    monkeypatch.setattr(settings, "enable_opensearch", True)
    observed = []

    class FakeOpenSearch:
        def __init__(self, **kwargs):
            self.closed = False

        async def search(self, **kwargs):
            observed.append(kwargs)
            return {"hits": {"hits": []}}

        async def close(self):
            self.closed = True

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = FakeOpenSearch
    monkeypatch.setitem(sys.modules, "opensearchpy", module)

    with TestClient(main.app) as client:
        for tenant in TENANTS:
            for service in ("checkout", "payments"):
                response = client.post(
                    "/api/v1/observability/logs/search",
                    json=payload(service),
                    headers=signed_headers(monkeypatch, tenant, service),
                )
                assert response.status_code == 200, response.text
                assert response.headers["cache-control"] == "no-store"

    assert len(observed) == 4
    for call, (tenant, service) in zip(
        observed,
        [(tenant, service) for tenant in TENANTS for service in ("checkout", "payments")],
    ):
        filters = call["body"]["query"]["bool"]["filter"]
        assert {"term": {"tenant.id": str(tenant)}} in filters
        assert {"term": {"resource.attributes.service.name": service}} in filters
        assert call["body"]["size"] == 4


def test_http_to_adapter_backend_error_is_sanitized(monkeypatch, replay_unit):
    monkeypatch.setattr(settings, "internal_api_key", KEY)
    monkeypatch.setattr(settings, "enable_opensearch", True)
    state = {"closed": False}

    class FakeOpenSearch:
        def __init__(self, **kwargs):
            pass

        async def search(self, **kwargs):
            raise TimeoutError("secret@search.internal/private-index")

        async def close(self):
            state["closed"] = True

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = FakeOpenSearch
    monkeypatch.setitem(sys.modules, "opensearchpy", module)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/v1/observability/logs/search",
            json=payload("checkout"),
            headers=signed_headers(monkeypatch, TENANTS[0]),
        )
    assert response.status_code == 502
    assert response.json() == {"detail": "OpenSearch query failed"}
    assert response.headers["cache-control"] == "no-store"
    assert "private-index" not in response.text
    assert state["closed"] is True


def test_unauthorized_http_never_constructs_opensearch_client(monkeypatch, replay_unit):
    monkeypatch.setattr(settings, "internal_api_key", KEY)
    monkeypatch.setattr(settings, "enable_opensearch", True)

    class ForbiddenClient:
        def __init__(self, **kwargs):
            raise AssertionError("Unauthorized caller reached OpenSearch")

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = ForbiddenClient
    monkeypatch.setitem(sys.modules, "opensearchpy", module)

    with TestClient(main.app) as client:
        for headers, expected in (
            ({"X-Tenant-ID": str(TENANTS[0])}, 401),
            ({"X-Internal-API-Key": "wrong", "X-Tenant-ID": str(TENANTS[0])}, 401),
            ({"X-Internal-API-Key": KEY, "X-Tenant-ID": "invalid"}, 401),
            (signed_headers(monkeypatch, TENANTS[0], "payments"), 403),
        ):
            response = client.post(
                "/api/v1/observability/logs/search",
                json=payload("checkout"), headers=headers,
            )
            assert response.status_code == expected, response.text
    replay_unit.assert_awaited_once()


def test_replay_failure_never_constructs_opensearch_client(monkeypatch, replay_unit):
    monkeypatch.setattr(settings, "internal_api_key", KEY)
    monkeypatch.setattr(settings, "enable_opensearch", True)

    class ForbiddenClient:
        def __init__(self, **kwargs):
            raise AssertionError("Replay failure reached OpenSearch")

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = ForbiddenClient
    monkeypatch.setitem(sys.modules, "opensearchpy", module)
    with TestClient(main.app) as client:
        replay_unit.return_value = False
        duplicate = client.post("/api/v1/observability/logs/search", json=payload("checkout"),
                                headers=signed_headers(monkeypatch, TENANTS[0]))
        replay_unit.side_effect = RuntimeError("private database details")
        unavailable = client.post("/api/v1/observability/logs/search", json=payload("checkout"),
                                  headers=signed_headers(monkeypatch, TENANTS[0]))
    assert duplicate.status_code == 401
    assert unavailable.status_code == 503
    assert "private database details" not in unavailable.text
    assert duplicate.headers["cache-control"] == unavailable.headers["cache-control"] == "no-store"
    assert replay_unit.await_count == 2
