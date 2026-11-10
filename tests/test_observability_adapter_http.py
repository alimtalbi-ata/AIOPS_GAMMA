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


def test_http_to_adapter_scopes_each_tenant_and_service(monkeypatch):
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
                    headers={
                        "X-Internal-API-Key": KEY,
                        "X-Tenant-ID": str(tenant),
                    },
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


def test_http_to_adapter_backend_error_is_sanitized(monkeypatch):
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
            headers={
                "X-Internal-API-Key": KEY,
                "X-Tenant-ID": str(TENANTS[0]),
            },
        )
    assert response.status_code == 502
    assert response.json() == {"detail": "OpenSearch query failed"}
    assert response.headers["cache-control"] == "no-store"
    assert "private-index" not in response.text
    assert state["closed"] is True
