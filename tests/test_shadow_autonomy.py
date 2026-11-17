"""Offline UC06→UC08 autonomy decision tests; no runtime services or actions."""
import pytest

from app.reused.shadow_autonomy import assess_shadow_autonomy


BASE = dict(
    evidence_source_verified=True,
    topology_source_verified=True,
    rca_verdict="supported",
    supporting_evidence_count=2,
    contradicting_evidence_count=0,
    runbook_approved=True,
    policy_approved=True,
    hitl_approved=True,
)


def test_fully_qualified_shadow_candidate_still_never_executes():
    result = assess_shadow_autonomy(**BASE)
    assert result.state == "REVIEW_CANDIDATE"
    assert result.proposed_next_step == "INDEPENDENT_EXECUTION_AUTHORIZATION_REQUIRED"
    assert result.authoritative is False
    assert result.live_execution_authorized is False


@pytest.mark.parametrize("overrides, reason", [
    ({"evidence_source_verified": False}, "EVIDENCE_UNVERIFIED"),
    ({"topology_source_verified": False}, "TOPOLOGY_UNVERIFIED"),
    ({"rca_verdict": "unknown"}, "RCA_NOT_SUPPORTED"),
    ({"rca_verdict": "rejected"}, "RCA_NOT_SUPPORTED"),
    ({"supporting_evidence_count": 0}, "NO_SUPPORTING_EVIDENCE"),
    ({"contradicting_evidence_count": 1}, "CONTRADICTING_EVIDENCE"),
    ({"runbook_approved": False}, "RUNBOOK_UNAPPROVED"),
    ({"policy_approved": False}, "POLICY_UNAPPROVED"),
    ({"hitl_approved": False}, "HITL_MISSING"),
])
def test_shadow_abstains_when_any_qualification_is_missing(overrides, reason):
    result = assess_shadow_autonomy(**(BASE | overrides))
    assert result.state == "ABSTAIN"
    assert reason in result.reasons
    assert result.live_execution_authorized is False


def test_shadow_collects_multiple_explanations_for_operator():
    result = assess_shadow_autonomy(**(BASE | {
        "evidence_source_verified": False,
        "rca_verdict": "unknown",
        "policy_approved": False,
    }))
    assert result.reasons == (
        "EVIDENCE_UNVERIFIED", "RCA_NOT_SUPPORTED", "POLICY_UNAPPROVED"
    )


@pytest.mark.parametrize("overrides", [
    {"supporting_evidence_count": -1},
    {"supporting_evidence_count": True},
    {"contradicting_evidence_count": -1},
    {"contradicting_evidence_count": False},
    {"rca_verdict": "hallucinated"},
    {"policy_approved": "yes"},
])
def test_shadow_rejects_invalid_inputs(overrides):
    with pytest.raises(ValueError):
        assess_shadow_autonomy(**(BASE | overrides))
