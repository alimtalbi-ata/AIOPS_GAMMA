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


@pytest.mark.asyncio
async def test_mutated_query_is_rejected_before_client_import_or_network(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "max_query_hours", 24)
    req = request()
    req.limit = 1000000
    # This intentionally fails before the lazy opensearchpy import.
    with pytest.raises(ValueError):
        await search_logs(TENANT, req)


@pytest.mark.asyncio
async def test_backend_receives_all_mandatory_scoping_filters(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "max_query_hours", 24)
    observed = {}

    class FakeClient:
        async def search(self, **kwargs):
            observed.update(kwargs)
            return {"hits": {"hits": []}}

        async def close(self):
            observed["closed"] = True

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = lambda **kwargs: FakeClient()
    monkeypatch.setitem(sys.modules, "opensearchpy", module)
    req = request()
    req.severity = ["ERROR"]
    await search_logs(TENANT, req)
    filters = observed["body"]["query"]["bool"]["filter"]
    assert {"term": {"tenant.id": TENANT}} in filters
    assert {"term": {"resource.attributes.service.name": "checkout"}} in filters
    assert {"terms": {"severityText": ["ERROR"]}} in filters
    assert observed["body"]["track_total_hits"] is False
    assert observed["closed"] is True


@pytest.mark.asyncio
async def test_request_mutation_during_backend_call_cannot_change_response_scope(monkeypatch):
    """The query and returned hits must be checked against the same request snapshot."""
    from app.settings import settings

    monkeypatch.setattr(settings, "max_query_hours", 24)
    req = request()
    closed = []

    class FakeClient:
        async def search(self, **kwargs):
            req.service_name = "billing"
            return {"hits": {"hits": [{
                "_source": {
                    "tenant": {"id": TENANT},
                    "resource": {"attributes": {"service.name": "billing"}},
                },
            }]}}

        async def close(self):
            closed.append(True)

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = lambda **kwargs: FakeClient()
    monkeypatch.setitem(sys.modules, "opensearchpy", module)
    with pytest.raises(ValueError, match="tenant or service scope"):
        await search_logs(TENANT, req)
    assert closed == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant,service,timestamp,accepted", [
    (TENANT, "checkout", "2026-11-10T11:57:00Z", True),
    ("22222222-2222-4222-8222-222222222222", "checkout", "2026-11-10T11:57:00Z", False),
    (TENANT, "billing", "2026-11-10T11:57:00Z", False),
    (TENANT, "checkout", "2026-11-10T10:57:00Z", False),
    (TENANT, "checkout", None, False),
])
async def test_real_adapter_validates_nonempty_backend_hits(monkeypatch, tenant, service, timestamp, accepted):
    """Exercise the actual adapter boundary rather than only its validation helper."""
    from app.settings import settings

    monkeypatch.setattr(settings, "max_query_hours", 24)
    closed = []

    class FakeClient:
        async def search(self, **kwargs):
            return {"hits": {"hits": [{"_source": {
                "tenant": {"id": tenant},
                "resource": {"attributes": {"service.name": service}},
                "@timestamp": timestamp,
            }}]}}

        async def close(self):
            closed.append(True)

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = lambda **kwargs: FakeClient()
    monkeypatch.setitem(sys.modules, "opensearchpy", module)

    if accepted:
        response = await search_logs(TENANT, request())
        assert len(response["hits"]["hits"]) == 1
    else:
        with pytest.raises(ValueError, match="OpenSearch hit"):
            await search_logs(TENANT, request())
    assert closed == [True]


@pytest.mark.asyncio
async def test_severity_filter_enforced_at_actual_adapter_boundary(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "max_query_hours", 24)
    closed = []
    observed = {}

    class FakeClient:
        async def search(self, **kwargs):
            observed.update(kwargs)
            return {"hits": {"hits": [{"_source": {
                "tenant": {"id": TENANT},
                "resource": {"attributes": {"service.name": "checkout"}},
                "@timestamp": "2026-11-10T11:57:00Z",
                "severityText": "WARN",
            }}]}}

        async def close(self):
            closed.append(True)

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = lambda **kwargs: FakeClient()
    monkeypatch.setitem(sys.modules, "opensearchpy", module)
    req = request()
    req.severity = ["ERROR"]
    with pytest.raises(ValueError, match="requested severity"):
        await search_logs(TENANT, req)
    assert {"terms": {"severityText": ["ERROR"]}} in observed["body"]["query"]["bool"]["filter"]
    assert closed == [True]


@pytest.mark.asyncio
async def test_adapter_never_returns_unreviewed_log_payload_fields(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "max_query_hours", 24)
    closed = []

    class FakeClient:
        async def search(self, **kwargs):
            return {"hits": {"hits": [{
                "_id": "sensitive-document-id",
                "_index": "internal-index",
                "_source": {
                    "tenant": {"id": TENANT, "internal_secret": "private"},
                    "resource": {"attributes": {
                        "service.name": "checkout", "auth.token": "private",
                    }},
                    "@timestamp": "2026-11-10T11:57:00Z",
                    "severityText": "ERROR",
                    "body": "Authorization: Bearer sensitive",
                    "user.email": "private@example.invalid",
                },
                "highlight": {"body": ["secret"]},
            }]}, "_shards": {"failed": 0}}

        async def close(self):
            closed.append(True)

    module = ModuleType("opensearchpy")
    module.AsyncOpenSearch = lambda **kwargs: FakeClient()
    monkeypatch.setitem(sys.modules, "opensearchpy", module)
    response = await search_logs(TENANT, request())
    assert response == {"hits": {"hits": [{"_source": {
        "tenant": {"id": TENANT},
        "resource": {"attributes": {"service.name": "checkout"}},
        "@timestamp": "2026-11-10T11:57:00Z",
        "severityText": "ERROR",
    }}]}}
    assert closed == [True]
