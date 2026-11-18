from dataclasses import replace
import pytest
from app.reused.shadow_remediation_risk import SyntheticRiskInput, screen_risk

BASE = SyntheticRiskInput("low", 1, True, True, True)


def test_low_risk_is_review_only():
    result = screen_risk(BASE)
    assert result["state"] == "REVIEW_CANDIDATE"
    assert result["live_execution_authorized"] is False
    assert result["human_review_required"] is True


@pytest.mark.parametrize("change,reason", [
    ({"criticality": "critical"}, "HIGH_CRITICALITY"),
    ({"affected_services": 2}, "MULTI_SERVICE_IMPACT"),
    ({"preconditions_verified": False}, "PRECONDITIONS_UNVERIFIED"),
    ({"rollback_tested": False}, "ROLLBACK_UNTESTED"),
    ({"maintenance_window_open": False}, "OUTSIDE_MAINTENANCE_WINDOW"),
])
def test_risk_blocks(change, reason):
    result = screen_risk(replace(BASE, **change))
    assert result["state"] == "BLOCKED"
    assert reason in result["reasons"]
    assert result["live_execution_authorized"] is False


def test_truthy_non_boolean_rejected():
    with pytest.raises(ValueError):
        screen_risk(replace(BASE, rollback_tested="true"))
