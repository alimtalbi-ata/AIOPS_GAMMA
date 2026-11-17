"""Pure shadow runbook selection: no agent, tool call, or execution."""
import pytest

from app.reused.shadow_runbook import RunbookCandidate, plan_shadow_runbook


RUNBOOK = RunbookCandidate(
    runbook_id="rb-checkout-latency", version="v1",
    service="checkout", symptom="latency",
    approved=True, rollback_defined=True,
    verification_sli="checkout_request_latency_p95_ms",
)


def test_unique_approved_recipe_only_proposes_review_and_unmeasured_sli():
    plan = plan_shadow_runbook(service="checkout", symptom="latency",
                               catalog=(RUNBOOK,), rca_supported=True)
    assert plan.state == "REVIEW_CANDIDATE"
    assert plan.runbook_id == "rb-checkout-latency"
    assert plan.runbook_version == "v1"
    assert plan.verification_sli == "checkout_request_latency_p95_ms"
    assert plan.verification_state == "NOT_MEASURED"
    assert plan.authoritative is False
    assert plan.live_execution_authorized is False


@pytest.mark.parametrize("catalog,rca,reason", [
    ((), True, "NO_MATCHING_RUNBOOK"),
    ((RUNBOOK,), False, "RCA_NOT_SUPPORTED"),
    ((RUNBOOK, RUNBOOK), True, "AMBIGUOUS_RUNBOOK"),
    ((RunbookCandidate(**(RUNBOOK.__dict__ | {"approved": False})),), True, "RUNBOOK_UNAPPROVED"),
    ((RunbookCandidate(**(RUNBOOK.__dict__ | {"rollback_defined": False})),), True, "ROLLBACK_UNDEFINED"),
])
def test_abstention_never_selects_runbook(catalog, rca, reason):
    plan = plan_shadow_runbook(service="checkout", symptom="latency",
                               catalog=catalog, rca_supported=rca)
    assert plan.state == "ABSTAIN"
    assert reason in plan.reasons
    assert plan.runbook_id is None
    assert plan.live_execution_authorized is False


def test_wrong_service_cannot_select_other_tenant_like_catalog_entry():
    plan = plan_shadow_runbook(service="payments", symptom="latency",
                               catalog=(RUNBOOK,), rca_supported=True)
    assert plan.state == "ABSTAIN"
    assert "NO_MATCHING_RUNBOOK" in plan.reasons


@pytest.mark.parametrize("catalog", [
    [RUNBOOK],
    (RunbookCandidate(**(RUNBOOK.__dict__ | {"verification_sli": ""})),),
    (RunbookCandidate(**(RUNBOOK.__dict__ | {"approved": 1})),),
])
def test_rejects_invalid_catalog(catalog):
    with pytest.raises(ValueError):
        plan_shadow_runbook(service="checkout", symptom="latency",
                            catalog=catalog, rca_supported=True)
