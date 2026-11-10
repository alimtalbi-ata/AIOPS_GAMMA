"""OpenSearch tenant query contract.

These tests validate the query builder, not OpenSearch index mappings or DLS.
A real multi-tenant staging test remains mandatory before enabling the adapter.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.opensearch_adapter import make_log_query
from app.schemas import LogSearchRequest, TimeWindow

TENANTS = (
    UUID("11111111-1111-4111-8111-111111111111"),
    UUID("22222222-2222-4222-8222-222222222222"),
)
SERVICES = ("checkout", "payments")


@pytest.mark.parametrize("tenant", TENANTS)
@pytest.mark.parametrize("service", SERVICES)
@pytest.mark.parametrize("severity", [[], ["ERROR", "WARN"]])
def test_query_scopes_every_tenant_service_and_severity(tenant, service, severity):
    end = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    start = end - timedelta(minutes=15)
    req = LogSearchRequest(
        service_name=service,
        window=TimeWindow(start=start, end=end),
        severity=severity,
        limit=17,
    )
    query = make_log_query(str(tenant), req)
    filters = query["query"]["bool"]["filter"]
    assert query["size"] == 17
    assert query["track_total_hits"] is False
    assert query["sort"] == [{"@timestamp": {"order": "desc"}}]
    assert {"term": {"tenant.id": str(tenant)}} in filters
    assert {"term": {"resource.attributes.service.name": service}} in filters
    assert {"range": {"@timestamp": {
        "gte": start.isoformat(), "lte": end.isoformat(),
    }}} in filters
    assert ({"terms": {"severityText": severity}} in filters) is bool(severity)
    assert len(filters) == (4 if severity else 3)
    other_tenant = next(t for t in TENANTS if t != tenant)
    other_service = next(s for s in SERVICES if s != service)
    assert str(other_tenant) not in str(query)
    assert other_service not in str(query)


def test_query_uses_filter_context_without_user_supplied_dsl():
    end = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    req = LogSearchRequest(
        service_name="checkout",
        window=TimeWindow(start=end - timedelta(minutes=1), end=end),
    )
    query = make_log_query(str(TENANTS[0]), req)
    assert set(query["query"]["bool"]) == {"filter"}
    assert "script" not in str(query)
    assert "query_string" not in str(query)


@pytest.mark.parametrize("tenant", [
    "", " ", "not-a-uuid", "11111111-1111-4111-8111-111111111111 ",
    "11111111111141118111111111111111",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa".upper(),
])
def test_query_builder_rejects_invalid_or_noncanonical_tenant(tenant):
    end = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    req = LogSearchRequest(
        service_name="checkout",
        window=TimeWindow(start=end - timedelta(minutes=1), end=end),
    )
    with pytest.raises(ValueError, match="tenant UUID"):
        make_log_query(tenant, req)


@pytest.mark.asyncio
async def test_invalid_tenant_never_initializes_opensearch_client(monkeypatch):
    import sys
    from types import ModuleType
    from app.opensearch_adapter import search_logs

    fake_module = ModuleType("opensearchpy")

    class ForbiddenClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("OpenSearch client must not be constructed")

    fake_module.AsyncOpenSearch = ForbiddenClient
    monkeypatch.setitem(sys.modules, "opensearchpy", fake_module)
    end = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    req = LogSearchRequest(
        service_name="checkout",
        window=TimeWindow(start=end - timedelta(minutes=1), end=end),
    )
    with pytest.raises(ValueError, match="tenant UUID"):
        await search_logs("not-a-uuid", req)
