"""Isolated tests of the actual OpenSearch adapter's client lifecycle.

No network or database access. These checks do not establish staging DLS.
"""
from datetime import datetime, timedelta, timezone
from types import ModuleType
import sys

import pytest

from app.opensearch_adapter import search_logs
from app.schemas import LogSearchRequest, TimeWindow

TENANT = "11111111-1111-4111-8111-111111111111"


def request():
    end = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    return LogSearchRequest(
        service_name="checkout",
        window=TimeWindow(start=end - timedelta(minutes=5), end=end),
        limit=3,
    )


@pytest.mark.asyncio
async def test_opensearch_client_closed_after_success(monkeypatch):
    clients = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.closed = False
            clients.append(self)

        async def search(self, **kwargs):
            assert kwargs["body"]["query"]["bool"]["filter"][0] == {
                "term": {"tenant.id": TENANT},
            }
            assert kwargs["request_timeout"] == 10
            return {"hits": {"hits": []}}

        async def close(self):
            self.closed = True

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = FakeClient
    monkeypatch.setitem(sys.modules, "opensearchpy", module)

    assert await search_logs(TENANT, request()) == {"hits": {"hits": []}}
    assert len(clients) == 1 and clients[0].closed


@pytest.mark.asyncio
async def test_opensearch_client_closed_after_backend_error(monkeypatch):
    clients = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.closed = False
            clients.append(self)

        async def search(self, **kwargs):
            raise TimeoutError("backend unavailable")

        async def close(self):
            self.closed = True

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = FakeClient
    monkeypatch.setitem(sys.modules, "opensearchpy", module)

    with pytest.raises(TimeoutError):
        await search_logs(TENANT, request())
    assert len(clients) == 1 and clients[0].closed


@pytest.mark.asyncio
async def test_invalid_tenant_does_not_construct_opensearch_client(monkeypatch):
    class ForbiddenClient:
        def __init__(self, **kwargs):
            raise AssertionError("OpenSearch client constructed")

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = ForbiddenClient
    monkeypatch.setitem(sys.modules, "opensearchpy", module)

    with pytest.raises(ValueError, match="tenant UUID"):
        await search_logs("invalid", request())


@pytest.mark.asyncio
async def test_backend_receives_configured_index_and_security_options(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "opensearch_logs_index", "staging-logs-*")
    monkeypatch.setattr(settings, "opensearch_url", "https://search.internal:9200")
    monkeypatch.setattr(settings, "opensearch_username", "readonly")
    monkeypatch.setattr(settings, "opensearch_password", "test-secret")
    monkeypatch.setattr(settings, "opensearch_verify_certs", True)
    monkeypatch.setattr(settings, "opensearch_ca_certs", "/etc/ssl/staging-ca.pem")
    observed = {}

    class FakeClient:
        def __init__(self, **kwargs):
            observed["init"] = kwargs

        async def search(self, **kwargs):
            observed["search"] = kwargs
            return {"hits": {"hits": []}}

        async def close(self):
            observed["closed"] = True

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = FakeClient
    monkeypatch.setitem(sys.modules, "opensearchpy", module)

    await search_logs(TENANT, request())
    assert observed["init"]["hosts"] == ["https://search.internal:9200"]
    assert observed["init"]["http_auth"] == ("readonly", "test-secret")
    assert observed["init"]["verify_certs"] is True
    assert observed["init"]["ca_certs"] == "/etc/ssl/staging-ca.pem"
    assert observed["search"]["index"] == "staging-logs-*"
    assert observed["search"]["body"]["size"] == 3
    assert observed["closed"] is True
