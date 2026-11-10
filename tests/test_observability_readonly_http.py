"""Read-only observability HTTP contract, using the real FastAPI app.

The OpenSearch network boundary is replaced by a deterministic fake; no external
services or database are needed. This does not certify OpenSearch ACLs.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi.testclient import TestClient

import app.main as main
from app.settings import settings

TENANT_A = UUID("11111111-1111-4111-8111-111111111111")
TENANT_B = UUID("22222222-2222-4222-8222-222222222222")
KEY = "observability-test-key"


def body():
    end = datetime.now(timezone.utc)
    return {
        "service_name": "checkout",
        "window": {
            "start": (end - timedelta(minutes=5)).isoformat(),
            "end": end.isoformat(),
        },
        "limit": 5,
    }


def headers(tenant):
    return {"X-Internal-API-Key": KEY, "X-Tenant-ID": str(tenant)}


def test_logs_disabled_fail_closed_without_opening_backend(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", KEY)
    monkeypatch.setattr(settings, "enable_opensearch", False)

    async def unexpected_backend(*args, **kwargs):
        raise AssertionError("Disabled OpenSearch adapter was invoked")

    monkeypatch.setattr(main, "search_logs", unexpected_backend)
    with TestClient(main.app) as client:
        response = client.post("/api/v1/observability/logs/search",
                               json=body(), headers=headers(TENANT_A))
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"


def test_logs_forward_only_authenticated_tenant_to_backend(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", KEY)
    monkeypatch.setattr(settings, "enable_opensearch", True)
    observed = []

    async def fake_backend(tenant_id, request):
        observed.append((tenant_id, request.service_name, request.limit))
        return {"hits": {"hits": []}}

    monkeypatch.setattr(main, "search_logs", fake_backend)
    with TestClient(main.app) as client:
        for tenant in (TENANT_A, TENANT_B):
            response = client.post("/api/v1/observability/logs/search",
                                   json=body(), headers=headers(tenant))
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "no-store"
            assert response.json() == {"hits": {"hits": []}}
    assert observed == [
        (str(TENANT_A), "checkout", 5),
        (str(TENANT_B), "checkout", 5),
    ]


def test_logs_reject_bad_auth_before_backend(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", KEY)
    monkeypatch.setattr(settings, "enable_opensearch", True)

    async def unexpected_backend(*args, **kwargs):
        raise AssertionError("Unauthorized request reached backend")

    monkeypatch.setattr(main, "search_logs", unexpected_backend)
    with TestClient(main.app) as client:
        response = client.post("/api/v1/observability/logs/search",
                               json=body(), headers={"X-Tenant-ID": str(TENANT_A)})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_logs_reject_oversized_time_window_before_backend(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", KEY)
    monkeypatch.setattr(settings, "enable_opensearch", True)
    monkeypatch.setattr(settings, "max_query_hours", 1)

    async def unexpected_backend(*args, **kwargs):
        raise AssertionError("Oversized request reached backend")

    monkeypatch.setattr(main, "search_logs", unexpected_backend)
    payload = body()
    payload["window"]["start"] = (
        datetime.fromisoformat(payload["window"]["end"]) - timedelta(hours=2)
    ).isoformat()
    with TestClient(main.app) as client:
        response = client.post("/api/v1/observability/logs/search",
                               json=payload, headers=headers(TENANT_A))
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


def test_logs_reject_invalid_tenant_before_backend(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", KEY)
    monkeypatch.setattr(settings, "enable_opensearch", True)

    async def unexpected_backend(*args, **kwargs):
        raise AssertionError("Invalid tenant reached backend")

    monkeypatch.setattr(main, "search_logs", unexpected_backend)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/v1/observability/logs/search",
            json=body(),
            headers={
                "X-Internal-API-Key": KEY,
                "X-Tenant-ID": "not-a-uuid",
            },
        )
    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"


def test_logs_backend_failure_is_sanitized_and_not_cached(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", KEY)
    monkeypatch.setattr(settings, "enable_opensearch", True)

    async def broken_backend(*args, **kwargs):
        raise RuntimeError("secret-user:secret-password@internal-search:9200/private-index")

    monkeypatch.setattr(main, "search_logs", broken_backend)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/v1/observability/logs/search",
            json=body(), headers=headers(TENANT_A),
        )
    assert response.status_code == 502
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "OpenSearch query failed"}
    assert "secret-password" not in response.text
    assert "private-index" not in response.text


def test_logs_reject_invalid_request_without_cache(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", KEY)
    monkeypatch.setattr(settings, "enable_opensearch", True)

    async def unexpected_backend(*args, **kwargs):
        raise AssertionError("Invalid request reached backend")

    monkeypatch.setattr(main, "search_logs", unexpected_backend)
    payload = body()
    payload["service_name"] = "invalid service name!"
    with TestClient(main.app) as client:
        response = client.post(
            "/api/v1/observability/logs/search",
            json=payload, headers=headers(TENANT_A),
        )
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


def test_logs_unconfigured_internal_auth_fails_closed_without_backend(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "")
    monkeypatch.setattr(settings, "enable_opensearch", True)

    async def unexpected_backend(*args, **kwargs):
        raise AssertionError("Unconfigured authentication reached backend")

    monkeypatch.setattr(main, "search_logs", unexpected_backend)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/v1/observability/logs/search",
            json=body(),
            headers={"X-Tenant-ID": str(TENANT_A)},
        )
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "Internal authentication not configured"}
