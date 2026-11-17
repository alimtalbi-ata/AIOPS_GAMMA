"""P2 defense-in-depth: direct OpenSearch adapter calls respect window limits."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.opensearch_adapter import make_log_query, search_logs
from app.schemas import LogSearchRequest, TimeWindow
from app.settings import settings


def query(hours):
    start = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    return LogSearchRequest(
        service_name="checkout",
        window=TimeWindow(start=start, end=start + timedelta(hours=hours)),
    )


def test_maximum_window_is_allowed(monkeypatch):
    monkeypatch.setattr(settings, "max_query_hours", 24)
    built = make_log_query(str(uuid4()), query(24))
    assert built["size"] == 100


@pytest.mark.parametrize("hours", [25, 48, 168])
def test_excessive_window_is_rejected_for_direct_adapter_call(monkeypatch, hours):
    monkeypatch.setattr(settings, "max_query_hours", 24)
    with pytest.raises(ValueError, match="window exceeds policy"):
        make_log_query(str(uuid4()), query(hours))


@pytest.mark.asyncio
async def test_excessive_window_rejected_before_opening_opensearch_client(monkeypatch):
    monkeypatch.setattr(settings, "max_query_hours", 24)
    with pytest.raises(ValueError, match="window exceeds policy"):
        await search_logs(str(uuid4()), query(25))


@pytest.mark.parametrize("invalid_policy", [0, -1])
def test_invalid_configured_window_policy_fails_closed(monkeypatch, invalid_policy):
    monkeypatch.setattr(settings, "max_query_hours", invalid_policy)
    with pytest.raises(ValueError, match="policy must be positive"):
        make_log_query(str(uuid4()), query(1))


def test_mutated_time_window_cannot_bypass_adapter_validation(monkeypatch):
    monkeypatch.setattr(settings, "max_query_hours", 24)
    req = query(1)
    req.window.end = req.window.start
    with pytest.raises(ValueError, match="increasing timestamps"):
        make_log_query(str(uuid4()), req)


def test_mutated_query_limit_cannot_bypass_adapter_validation(monkeypatch):
    monkeypatch.setattr(settings, "max_query_hours", 24)
    req = query(1)
    req.limit = 1000000
    with pytest.raises(ValueError):
        make_log_query(str(uuid4()), req)


def test_mutated_service_name_cannot_bypass_adapter_validation(monkeypatch):
    monkeypatch.setattr(settings, "max_query_hours", 24)
    req = query(1)
    req.service_name = "*"
    with pytest.raises(ValueError):
        make_log_query(str(uuid4()), req)
