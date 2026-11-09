from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.main import app
from app.opensearch_adapter import make_log_query
from app.schemas import LogSearchRequest, TimeWindow

client = TestClient(app)


def test_health():
    result = client.get("/api/v1/health/live")
    assert result.status_code == 200
    assert result.json()["status"] == "ok"


def test_private_endpoint_fails_closed():
    now = datetime.now(timezone.utc)
    result = client.post("/api/v1/observability/logs/search", json={
        "service_name": "payment-api",
        "window": {"start": (now-timedelta(minutes=5)).isoformat(), "end": now.isoformat()}
    })
    assert result.status_code in (401, 503)


def test_timestamp_order_rejected():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        TimeWindow(start=now, end=now-timedelta(seconds=5))


def test_query_enforces_tenant_and_service():
    now = datetime.now(timezone.utc)
    req = LogSearchRequest(
        service_name="checkout-api",
        window=TimeWindow(start=now-timedelta(minutes=10), end=now),
    )
    query = make_log_query(str(uuid4()), req)
    filters = query["query"]["bool"]["filter"]
    assert "tenant.id" in filters[0]["term"]
    assert filters[1] == {"term": {"resource.attributes.service.name": "checkout-api"}}
    assert query["size"] <= 500


def test_raw_promql_is_not_accepted():
    result = client.post("/api/v1/observability/metrics/query", json={"expression": "up"})
    assert result.status_code in (401, 503)
