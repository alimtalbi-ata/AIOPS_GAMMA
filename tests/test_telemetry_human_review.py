from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from app.reused.telemetry_human_review import ReviewDecision, review_preview
from app.reused.unified_telemetry import TelemetryObservation

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
TENANT = uuid4()


def run(**changes):
    items = [TelemetryObservation(tenant_id=TENANT, source=s, resource_id=s,
              external_id="event", source_version="v1", observed_at=NOW,
              fetched_at=NOW, value=1, metric=m)
             for s, m in [("sentinel", "anomalies_total"), ("arguslm", "latency_ms")]]
    args = dict(items=items, tenant_id=TENANT, incident_id="INC-1",
                reviewer_id="operator", review_grants=frozenset({(TENANT, "INC-1", "operator")}),
                grants=frozenset({("sentinel", "sentinel"), ("arguslm", "arguslm")}),
                bindings={("sentinel", "sentinel"): "svc", ("arguslm", "arguslm"): "svc"},
                now=NOW, snapshot_at=NOW)
    return review_preview(**(args | changes))


def decision(**changes):
    return ReviewDecision(**(dict(decision="reject_hypothesis", hypothesis_id="temporal-1",
        rationale="Insufficient verified evidence", snapshot_digest=run()["snapshot_digest"]) | changes))


def test_review_remains_preview():
    result = run(decision=decision())
    assert result["proposed_review"]["decision"] == "reject_hypothesis"
    for flag in ("persisted", "human_adjudicated", "authoritative",
                 "root_cause_confirmed", "live_remediation_authorized"):
        assert result[flag] is False


def test_scope():
    with pytest.raises(PermissionError):
        run(reviewer_id="other")


def test_snapshot_mismatch():
    with pytest.raises(ValueError):
        run(decision=decision(snapshot_digest="0"*64))


def test_expired():
    with pytest.raises(ValueError):
        run(now=NOW+timedelta(seconds=301))


def test_unknown_hypothesis():
    with pytest.raises(ValueError):
        run(decision=decision(hypothesis_id="unknown"))


def test_no_approval_intent():
    with pytest.raises(ValueError):
        decision(decision="approve_remediation")
