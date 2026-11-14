import math

import pytest

from app.reused.impact import estimate_impact


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), -float("inf"), -0.01, 1.01, "0.5", None])
def test_impact_rejects_invalid_direct_score(value):
    with pytest.raises(ValueError, match="direct_impact"):
        estimate_impact(value, 0, 1)


@pytest.mark.parametrize("redundant,total", [
    (True, 1), (0, False), (1.5, 2), (0, 1.5), (-1, 2), (3, 2),
])
def test_impact_rejects_invalid_path_counts(redundant, total):
    with pytest.raises(ValueError, match="path counts"):
        estimate_impact(0.5, redundant, total)


@pytest.mark.parametrize("direct,redundant,total,expected_state,expected_score", [
    (0.0, 0, 0, "UNKNOWN", 0.0),
    (0.1, 4, 4, "NONE", 0.1),
    (0.25, 3, 4, "DEGRADED", 0.25),
    (0.75, 1, 4, "OUTAGE", 0.75),
    (1.0, 0, 4, "OUTAGE", 1.0),
])
def test_impact_valid_boundaries(direct, redundant, total, expected_state, expected_score):
    result = estimate_impact(direct, redundant, total)
    assert result.state == expected_state
    assert result.score == expected_score
    assert result.source == "UNVERIFIED_TOPOLOGY_ESTIMATE"
    assert result.live_remediation_authorized is False
