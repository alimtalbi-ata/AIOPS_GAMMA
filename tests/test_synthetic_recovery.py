"""UC09 simulated recovery verification; no action, source read or rollback."""
from datetime import datetime, timedelta, timezone

import pytest

from app.reused.synthetic_recovery import SLIObservation, assess_synthetic_recovery


NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
BEFORE = SLIObservation(NOW, 800.0, 100)
AFTER = SLIObservation(NOW + timedelta(minutes=2), 150.0, 100)


def evaluate(before=BEFORE, after=AFTER, **kwargs):
    return assess_synthetic_recovery(
        before=before, after=after, max_acceptable_value=250.0, **kwargs,
    )


def test_recovered_is_non_authoritative():
    result = evaluate()
    assert result.state == "RECOVERED"
    assert result.rollback_proposal == "NONE"
    assert result.authoritative is False
    assert result.rollback_executed is False
    assert result.live_execution_authorized is False


def test_failed_recovery_proposes_only_rollback_review():
    result = evaluate(after=SLIObservation(AFTER.observed_at, 550.0, 100))
    assert result.state == "NOT_RECOVERED"
    assert result.reasons == ("SLI_STILL_BREACHED",)
    assert result.rollback_proposal == "REVIEW_ROLLBACK"
    assert result.rollback_executed is False


@pytest.mark.parametrize("before,after,reason", [
    (None, AFTER, "MISSING_MEASUREMENT"),
    (BEFORE, None, "MISSING_MEASUREMENT"),
    (BEFORE, SLIObservation(AFTER.observed_at, 100.0, 1), "INSUFFICIENT_SAMPLES"),
    (BEFORE, SLIObservation(NOW, 100.0, 100), "INVALID_MEASUREMENT_ORDER"),
    (BEFORE, SLIObservation(NOW + timedelta(minutes=10), 100.0, 100), "STALE_BASELINE"),
    (SLIObservation(NOW, 100.0, 100), AFTER, "NO_PRE_ACTION_BREACH"),
])
def test_unknown_abstains_on_unreliable_evidence(before, after, reason):
    result = evaluate(before=before, after=after)
    assert result.state == "UNKNOWN"
    assert reason in result.reasons
    assert result.rollback_proposal == "HUMAN_REVIEW_REQUIRED"
    assert result.live_execution_authorized is False


@pytest.mark.parametrize("observation", [
    SLIObservation(NOW, float("nan"), 100),
    SLIObservation(NOW, -1.0, 100),
    SLIObservation(NOW, 800.0, True),
    SLIObservation(NOW.replace(tzinfo=None), 800.0, 100),
])
def test_invalid_observations_fail_closed(observation):
    with pytest.raises(ValueError):
        evaluate(before=observation)


@pytest.mark.parametrize("policy", [
    {"min_samples": 0},
    {"min_samples": True},
    {"max_age": timedelta(0)},
])
def test_invalid_policy_fails_closed(policy):
    with pytest.raises(ValueError):
        evaluate(**policy)
