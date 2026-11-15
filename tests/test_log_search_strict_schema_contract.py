"""P2 OpenSearch read contract: reject ambiguous query parameters before adapter access."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas import LogSearchRequest, TimeWindow


START = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
END = START + timedelta(minutes=5)


def request(**changes):
    values = {
        "service_name": "checkout.api",
        "window": {"start": START, "end": END},
        "severity": ["error"],
        "limit": 100,
    }
    values.update(changes)
    return LogSearchRequest(**values)


def test_valid_log_query_preserves_bounded_filters():
    result = request()
    assert result.window.start == START
    assert result.service_name == "checkout.api"
    assert result.limit == 100


@pytest.mark.parametrize("unexpected", ["tenant_id", "index", "raw_query", "admin_override"])
def test_unknown_top_level_query_fields_rejected(unexpected):
    with pytest.raises(ValidationError):
        request(**{unexpected: "forged"})


@pytest.mark.parametrize("unexpected", ["timezone", "inclusive", "raw_query"])
def test_unknown_nested_time_window_fields_rejected(unexpected):
    with pytest.raises(ValidationError):
        request(window={"start": START, "end": END, unexpected: True})


@pytest.mark.parametrize("start,end", [
    (START.replace(tzinfo=None), END),
    (START, END.replace(tzinfo=None)),
    (END, START),
    (START, START),
])
def test_invalid_time_windows_rejected(start, end):
    with pytest.raises(ValidationError):
        TimeWindow(start=start, end=end)


@pytest.mark.parametrize("limit", [0, 501])
def test_query_limit_out_of_bounds_rejected(limit):
    with pytest.raises(ValidationError):
        request(limit=limit)
