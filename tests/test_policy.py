from app.reused.policy import RemediationProposal, evaluate


def proposal(**changes):
    args = {
        "mode": "LIVE", "command": "REMEDIATE", "severity": "P3",
        "confidence": 0.99, "evidence_count": 4, "critic_validated": True,
        "redundancy_ok": True, "evidence_fresh": True,
        "preconditions_verified": True, "fencing_verified": True,
        "human_approved": True, "recipe_approved": True,
        "asset_owner_verified": True, "low_risk": True,
    }
    args.update(changes)
    return RemediationProposal(**args)


def test_live_effect_never_authorized_by_client_flags():
    result = evaluate(proposal())
    assert result["state"] == "BLOCKED"
    assert result["live_execution_authorized"] is False


def test_p1_escalates_even_if_other_checks_pass():
    result = evaluate(proposal(severity="P1"))
    assert result["decision"] == "ESCALATE"
    assert not result["live_execution_authorized"]


def test_missing_runbook_blocks():
    assert "runbook" in evaluate(proposal(recipe_approved=False))["reason"]


def test_missing_evidence_is_unknown():
    assert evaluate(proposal(evidence_count=0))["state"] == "UNKNOWN"


def test_synthetic_only_simulates():
    result = evaluate(proposal(mode="REPLAY"))
    assert result["decision"] == "SIMULATE"
    assert result["live_execution_authorized"] is False


def test_read_only_decision_no_execution_grant():
    result = evaluate(proposal(command="OBSERVE"))
    assert result["decision"] == "ALLOW_READ_ONLY"
    assert result["live_execution_authorized"] is False


def test_all_live_effect_commands_require_independent_execution_gate():
    # Client-controlled approval flags must never grant an effectful LIVE action.
    for command in ("EXECUTE", "RESOLVE", "REMEDIATE", "CANCEL"):
        result = evaluate(proposal(command=command))
        assert result["state"] == "BLOCKED", (command, result)
        assert result["decision"] == "HUMAN_APPROVAL", (command, result)
        assert result["live_execution_authorized"] is False, (command, result)


def test_all_synthetic_modes_never_grant_live_execution():
    for mode in ("DEMO", "REPLAY", "STORY"):
        for command in ("EXECUTE", "RESOLVE", "REMEDIATE", "CANCEL"):
            result = evaluate(proposal(mode=mode, command=command))
            assert result["decision"] == "SIMULATE", (mode, command, result)
            assert result["live_execution_authorized"] is False, (mode, command, result)
