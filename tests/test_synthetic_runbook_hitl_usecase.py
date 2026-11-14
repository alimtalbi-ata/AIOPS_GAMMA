"""UC08/UC09: synthetic runbook decision and HITL boundary regression.

An advisory policy response is never an execution token, even when all
caller-controlled approval flags are true. No Temporal worker is invoked.
"""
import pytest

from app.reused.policy import RemediationProposal, evaluate


def proposal(*, mode="REPLAY", command="REMEDIATE", evidence_count=2,
             human_approved=True, recipe_approved=True):
    return RemediationProposal(
        mode=mode, command=command, severity="P3", confidence=0.99,
        evidence_count=evidence_count, critic_validated=True,
        redundancy_ok=True, evidence_fresh=True,
        preconditions_verified=True, fencing_verified=True,
        human_approved=human_approved, recipe_approved=recipe_approved,
        asset_owner_verified=True, low_risk=True,
    )


@pytest.mark.parametrize("mode", ["DEMO", "REPLAY", "STORY"])
def test_synthetic_runbook_proposal_is_simulation_only(mode):
    result = evaluate(proposal(mode=mode))
    assert result["decision"] == "SIMULATE"
    assert result["live_execution_authorized"] is False


@pytest.mark.parametrize("command", ["EXECUTE", "RESOLVE", "REMEDIATE", "CANCEL"])
def test_client_approval_flags_cannot_unlock_live_effect(command):
    result = evaluate(proposal(mode="LIVE", command=command))
    assert result["state"] == "BLOCKED"
    assert result["decision"] == "HUMAN_APPROVAL"
    assert result["live_execution_authorized"] is False


def test_missing_evidence_is_unknown_not_permission_to_execute():
    result = evaluate(proposal(evidence_count=0))
    assert result["state"] == "UNKNOWN"
    assert result["live_execution_authorized"] is False


def test_unapproved_runbook_blocks_live_proposal():
    result = evaluate(proposal(mode="LIVE", recipe_approved=False))
    assert result["state"] == "BLOCKED"
    assert "runbook" in result["reason"]
    assert result["live_execution_authorized"] is False


def test_human_approval_boolean_is_not_signed_hitl_receipt():
    approved = evaluate(proposal(mode="LIVE", human_approved=True))
    unapproved = evaluate(proposal(mode="LIVE", human_approved=False))
    assert approved["live_execution_authorized"] is False
    assert unapproved["live_execution_authorized"] is False
    assert approved["decision"] == unapproved["decision"] == "HUMAN_APPROVAL"
