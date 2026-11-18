from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.reused.telemetry_rca_critic import critique_telemetry
from app.reused.unified_telemetry import TelemetryObservation

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
TENANT = uuid4()


def row(source, **changes):
    base = dict(tenant_id=TENANT, source=source, resource_id=source,
                external_id="event", source_version="v1", observed_at=NOW,
                fetched_at=NOW, value=1,
                metric="anomalies_total" if source == "sentinel" else "latency_ms")
    return TelemetryObservation(**(base | changes))


def review(items, **changes):
    args = dict(tenant_id=TENANT, incident_id="INC-1", now=NOW,
                grants=frozenset({("sentinel", "sentinel"), ("arguslm", "arguslm")}),
                bindings={("sentinel", "sentinel"): "svc", ("arguslm", "arguslm"): "svc"})
    return critique_telemetry(items, **(args | changes))


def test_temporal_context_never_confirms_cause():
    result = review([row("sentinel"), row("arguslm")])
    assert result["decision"] == "INSUFFICIENT_EVIDENCE"
    assert result["reviews"][0]["verdict"] == "unknown"
    assert result["reviews"][0]["contradiction_state"] == "NOT_ASSESSED"
    assert result["reviews"][0]["confidence"] is None
    for flag in ("root_cause_confirmed", "model_invoked", "human_adjudicated",
                 "authoritative", "live_remediation_authorized"):
        assert result[flag] is False


def test_stale_and_missing_candidates_reported():
    result = review([row("sentinel"), row("arguslm", observed_at=NOW-timedelta(seconds=301))])
    assert "STALE_OBSERVATIONS_EXCLUDED" in result["findings"]
    assert "NO_CROSS_SOURCE_CANDIDATES" in result["findings"]
    assert result["reviews"] == []


def test_unmapped():
    assert "UNMAPPED_OBSERVATIONS_EXCLUDED" in review([row("sentinel")], bindings={})["findings"]


def test_cross_tenant_fails_closed():
    with pytest.raises(PermissionError):
        review([row("sentinel", tenant_id=uuid4())])


def test_truncation_reports_incomplete_coverage():
    rows = [row(source, external_id=str(i)) for source in ("sentinel", "arguslm") for i in range(25)]
    assert "INCOMPLETE_CANDIDATE_COVERAGE" in review(rows)["findings"]
