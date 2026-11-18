from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.reused.telemetry_copilot import copilot_preview
from app.reused.unified_telemetry import TelemetryObservation

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
TENANT = uuid4()


def row(source, **changes):
    data = dict(tenant_id=TENANT, source=source, resource_id=source,
                external_id="event", source_version="v1", observed_at=NOW,
                fetched_at=NOW, value=1,
                metric="anomalies_total" if source == "sentinel" else "latency_ms")
    return TelemetryObservation(**(data | changes))


def run(**changes):
    args = dict(items=[row("sentinel"), row("arguslm")], tenant_id=TENANT,
                incident_id="INC-1", incident_grants=frozenset({"INC-1"}),
                grants=frozenset({("sentinel", "sentinel"), ("arguslm", "arguslm")}),
                bindings={("sentinel", "sentinel"): "svc", ("arguslm", "arguslm"): "svc"},
                now=NOW)
    return copilot_preview(**(args | changes))


@pytest.mark.parametrize("intent", ["summary", "hypotheses", "blockers", "next_checks"])
def test_guided_intents_are_non_authoritative(intent):
    result = run(intent=intent)
    assert result["intent"] == intent
    assert result["answer"]
    assert result["decision"] == "INSUFFICIENT_EVIDENCE"
    assert result["model_invoked"] is False
    assert result["live_remediation_authorized"] is False


def test_context_refs_resolve():
    result = run(intent="hypotheses")
    assert {r["ref_id"] for r in result["context_references"]} == set(result["answer"]["context"][0]["context_refs"])


def test_incident_denied():
    with pytest.raises(PermissionError):
        run(incident_id="INC-2")


def test_cross_tenant_denied():
    with pytest.raises(PermissionError):
        run(items=[row("sentinel", tenant_id=uuid4())])


def test_action_intent_rejected():
    with pytest.raises(ValueError):
        run(intent="restart_service")
