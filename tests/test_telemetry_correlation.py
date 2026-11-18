from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from app.reused.unified_telemetry import TelemetryObservation
from app.reused.telemetry_correlation import correlate_telemetry

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
TENANT = uuid4()
GRANTS = frozenset({("sentinel", "s1"), ("arguslm", "a1")})
BINDINGS = {("sentinel", "s1"): "svc", ("arguslm", "a1"): "svc"}


def row(source, seconds=0, **changes):
    data = dict(tenant_id=TENANT, source=source,
                resource_id="s1" if source == "sentinel" else "a1",
                external_id="event", source_version="v1",
                observed_at=NOW-timedelta(seconds=seconds), fetched_at=NOW,
                metric="anomalies_total" if source == "sentinel" else "latency_ms",
                value=2)
    return TelemetryObservation(**(data | changes))


def run(items, **changes):
    return correlate_telemetry(items, **(dict(tenant_id=TENANT, grants=GRANTS,
        bindings=BINDINGS, now=NOW) | changes))


def test_candidate_is_not_causality():
    result = run([row("sentinel"), row("arguslm", 120)])
    assert result["candidate_count"] == 1
    assert result["candidates"][0]["distance_seconds"] == 120
    assert result["causality_established"] is False
    assert result["source_authenticated"] is False


def test_window_and_stale():
    assert run([row("sentinel"), row("arguslm", 121)])["candidate_count"] == 0
    result = run([row("sentinel"), row("arguslm", 301)], window_seconds=600)
    assert result["excluded"]["stale"] == 1
    assert result["candidate_count"] == 0


def test_no_implicit_binding():
    result = run([row("sentinel"), row("arguslm")], bindings={})
    assert result["excluded"]["unmapped"] == 2
    assert result["candidate_count"] == 0


def test_cross_tenant_rejected():
    with pytest.raises(PermissionError):
        run([row("sentinel"), row("arguslm", tenant_id=uuid4())])


def test_order_invariance():
    items = [row("sentinel"), row("arguslm", 10)]
    assert run(items) == run(list(reversed(items)))


def test_bounded_candidates():
    items = [row(source, external_id=str(i)) for source in ("sentinel", "arguslm") for i in range(25)]
    result = run(items)
    assert result["candidate_count"] == 625
    assert len(result["candidates"]) == 500
    assert result["truncated"] is True
