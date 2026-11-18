from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from app.reused.telemetry_rca_analyst import analyze_telemetry
from app.reused.unified_telemetry import TelemetryObservation

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
TENANT = uuid4()


def row(source, **changes):
    fields = dict(tenant_id=TENANT, source=source, resource_id=source,
                  external_id="event", source_version="v1", observed_at=NOW,
                  fetched_at=NOW, value=1,
                  metric="anomalies_total" if source == "sentinel" else "latency_ms")
    return TelemetryObservation(**(fields | changes))


def run(items, **changes):
    args = dict(tenant_id=TENANT, incident_id="INC-1", now=NOW,
                grants=frozenset({("sentinel", "sentinel"), ("arguslm", "arguslm")}),
                bindings={("sentinel", "sentinel"): "svc", ("arguslm", "arguslm"): "svc"})
    return analyze_telemetry(items, **(args | changes))


def test_unknown_with_resolvable_context():
    result = run([row("sentinel"), row("arguslm")])
    hypothesis, = result["investigation"]["hypotheses"]
    assert hypothesis["verdict"] == "unknown"
    assert hypothesis["supporting_refs"] == []
    question, = result["questions"]
    assert question["confidence"] is None
    assert set(question["context_refs"]) == {x["ref_id"] for x in result["investigation"]["evidence"]}
    assert result["evaluation"]["supported_hypotheses"] == 0
    assert result["root_cause_confirmed"] is False
    assert result["model_invoked"] is False


def test_no_pair_no_hypothesis():
    assert run([row("sentinel")])["questions"] == []
    assert run([row("sentinel"), row("arguslm", observed_at=NOW-timedelta(seconds=301))])["questions"] == []


def test_scope_rejected():
    with pytest.raises(PermissionError):
        run([row("sentinel", tenant_id=uuid4())])


def test_order_invariance():
    rows = [row("sentinel"), row("arguslm")]
    assert run(rows) == run(rows[::-1])
