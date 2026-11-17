"""Contract tests for synthetic AIOps incident decision journey."""
from datetime import datetime, timedelta, timezone

import pytest

from app.reused.shadow_incident_journey import IncidentShadowInput, evaluate_incident_shadow
from app.reused.shadow_investigation import Evidence, Hypothesis, InvestigationInput
from app.reused.shadow_runbook import RunbookCandidate
from app.reused.synthetic_recovery import SLIObservation


NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
RUNBOOK = RunbookCandidate(
    "rb-checkout-latency", "v1", "checkout", "latency",
    True, True, "checkout_request_latency_p95_ms",
)
BASE = dict(
    tenant_id="synthetic-tenant-1",
    incident_id="DEMO-INC-1",
    service="checkout",
    symptom="latency",
    evidence_verified=False,
    topology_verified=False,
    rca_verdict="unknown",
    supporting_refs=1,
    contradicting_refs=0,
    catalog=(RUNBOOK,),
)


def report(**overrides):
    return evaluate_incident_shadow(IncidentShadowInput(**(BASE | overrides)))


def test_unknown_rca_prevents_runbook_and_execution_and_recovery():
    result = report()
    assert result["mode"] == "synthetic_shadow"
    assert result["tenant_id"] == BASE["tenant_id"]
    assert result["incident_id"] == BASE["incident_id"]
    assert result["stages"]["runbook"]["state"] == "ABSTAIN"
    assert result["stages"]["autonomy"]["state"] == "ABSTAIN"
    assert result["stages"]["recovery"]["state"] == "UNKNOWN"
    assert result["execution_state"] == "NOT_EXECUTED"
    assert result["itsm_mutations_performed"] is False
    assert result["live_execution_authorized"] is False


def test_positive_caller_flags_still_never_grant_execution():
    result = report(
        evidence_verified=True, topology_verified=True,
        rca_verdict="supported", policy_approved=True, hitl_approved=True,
        simulated_action_performed=True,
        before=SLIObservation(NOW, 800.0, 100),
        after=SLIObservation(NOW + timedelta(minutes=2), 150.0, 100),
    )
    assert result["stages"]["runbook"]["state"] == "REVIEW_CANDIDATE"
    assert result["stages"]["autonomy"]["state"] == "REVIEW_CANDIDATE"
    assert result["stages"]["recovery"]["state"] == "RECOVERED"
    assert result["execution_state"] == "SYNTHETIC_ACTION_ONLY"
    assert result["authoritative"] is False
    assert result["live_execution_authorized"] is False


def test_failed_sli_proposes_review_not_rollback_execution():
    result = report(
        simulated_action_performed=True,
        before=SLIObservation(NOW, 800.0, 100),
        after=SLIObservation(NOW + timedelta(minutes=2), 500.0, 100),
    )
    assert result["stages"]["recovery"]["state"] == "NOT_RECOVERED"
    assert result["stages"]["recovery"]["rollback_proposal"] == "REVIEW_ROLLBACK"
    assert result["stages"]["recovery"]["rollback_executed"] is False


def test_no_action_cannot_claim_recovery_even_with_supplied_good_sli():
    result = report(
        before=SLIObservation(NOW, 800.0, 100),
        after=SLIObservation(NOW + timedelta(minutes=2), 100.0, 100),
    )
    assert result["stages"]["recovery"]["state"] == "UNKNOWN"
    assert "MISSING_MEASUREMENT" in result["stages"]["recovery"]["reasons"]
    assert result["execution_state"] == "NOT_EXECUTED"


def test_ambiguous_runbooks_block_even_claimed_approvals():
    result = report(
        evidence_verified=True, topology_verified=True,
        rca_verdict="supported", policy_approved=True, hitl_approved=True,
        catalog=(RUNBOOK, RUNBOOK),
    )
    assert result["stages"]["runbook"]["state"] == "ABSTAIN"
    assert "AMBIGUOUS_RUNBOOK" in result["stages"]["runbook"]["reasons"]
    assert result["stages"]["autonomy"]["state"] == "ABSTAIN"


@pytest.mark.parametrize("overrides", [
    {"tenant_id": ""},
    {"incident_id": "  "},
    {"supporting_refs": -1},
    {"rca_verdict": "hallucinated"},
    {"policy_approved": "yes"},
    {"simulated_action_performed": "yes"},
])
def test_invalid_inputs_fail_closed(overrides):
    with pytest.raises(ValueError):
        report(**overrides)


def investigation(tenant="synthetic-tenant-1", incident="DEMO-INC-1", contradictory=False):
    refs = [
        Evidence("metric", tenant, incident, "db", "supports", NOW, True, "metrics"),
        Evidence("trace", tenant, incident, "db", "supports", NOW, True, "traces"),
    ]
    if contradictory:
        refs.append(Evidence("counter", tenant, incident, "db", "contradicts", NOW, True, "logs"))
    return InvestigationInput(tenant, incident, (Hypothesis("db", "DB saturation"),), tuple(refs), NOW)


def test_attached_investigation_never_promotes_synthetic_evidence_to_authority():
    result = report(
        investigation=investigation(), evidence_verified=True, topology_verified=True,
        rca_verdict="supported", policy_approved=True, hitl_approved=True,
    )
    assert result["stages"]["investigation"]["state"] == "REVIEW_CANDIDATE"
    assert result["stages"]["runbook"]["state"] == "ABSTAIN"
    assert result["stages"]["autonomy"]["state"] == "ABSTAIN"
    assert result["live_execution_authorized"] is False


def test_contradictory_investigation_abstains_end_to_end():
    result = report(investigation=investigation(contradictory=True))
    assert result["stages"]["investigation"]["state"] == "ABSTAIN"
    assert result["stages"]["runbook"]["state"] == "ABSTAIN"
    assert result["stages"]["recovery"]["state"] == "UNKNOWN"


def test_cross_tenant_investigation_rejected_before_decision():
    with pytest.raises(ValueError, match="identity"):
        report(investigation=investigation(tenant="other"))


def test_cross_incident_investigation_rejected_before_decision():
    with pytest.raises(ValueError, match="identity"):
        report(investigation=investigation(incident="other"))
