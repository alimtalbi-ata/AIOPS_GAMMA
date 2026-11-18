from dataclasses import replace
import pytest
from test_shadow_inbox_rca import inputs
from test_shadow_remediation_preview import candidate
from app.reused.shadow_remediation_risk import SyntheticRiskInput
from app.reused.shadow_review_dossier import build_review_dossier


@pytest.mark.parametrize("catalog_ok,risk_ok,expected", [
    (True, True, "REVIEW_CANDIDATE"),
    (False, True, "BLOCKED"),
    (True, False, "BLOCKED"),
    (False, False, "BLOCKED"),
])
def test_combined_review_gate(catalog_ok, risk_ok, expected):
    receipt, investigation = inputs()
    risk = SyntheticRiskInput("low", 1, True, risk_ok, True)
    report = build_review_dossier(receipt, investigation, "payment", (), "timeout",
                                  (candidate(),) if catalog_ok else (), risk)
    assert report["review_state"] == expected
    assert report["approval_state"] == "NOT_GRANTED"
    assert report["execution_state"] == "NOT_EXECUTED"
    assert report["live_execution_authorized"] is False
    assert report["human_review_required"] is True
    if not risk_ok:
        assert "ROLLBACK_UNTESTED" in report["review_reasons"]
    if not catalog_ok:
        assert "NO_MATCHING_RUNBOOK" in report["review_reasons"]
