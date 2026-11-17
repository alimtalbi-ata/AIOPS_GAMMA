"""Pure synthetic post-remediation SLI assessment, without action or rollback.

Observations are caller supplied and NOT trusted monitoring data. No recovery
or rollback can be authorized by this evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite


@dataclass(frozen=True)
class SLIObservation:
    observed_at: datetime
    value: float
    sample_count: int


@dataclass(frozen=True)
class RecoveryAssessment:
    state: str
    reasons: tuple[str, ...]
    rollback_proposal: str
    authoritative: bool = False
    rollback_executed: bool = False
    live_execution_authorized: bool = False


def assess_synthetic_recovery(
    *,
    before: SLIObservation | None,
    after: SLIObservation | None,
    max_acceptable_value: float,
    min_samples: int = 20,
    max_age: timedelta = timedelta(minutes=5),
) -> RecoveryAssessment:
    """Evaluate a lower-is-better SLI, abstaining on untrustworthy samples.

    Recovery requires a measured pre-action breach, a later fresh measurement,
    enough samples on both sides and a post-action value within the threshold.
    """
    if (type(max_acceptable_value) not in (float, int)
            or not isfinite(max_acceptable_value) or max_acceptable_value <= 0
            or type(min_samples) is not int or min_samples < 1
            or not isinstance(max_age, timedelta) or max_age <= timedelta(0)):
        raise ValueError("Invalid recovery evaluation policy")
    reasons = []
    if before is None or after is None:
        reasons.append("MISSING_MEASUREMENT")
    else:
        for observation in (before, after):
            if type(observation) is not SLIObservation:
                raise ValueError("Invalid SLI observation")
            if (not isinstance(observation.observed_at, datetime)
                    or observation.observed_at.tzinfo is None
                    or observation.observed_at.utcoffset() is None
                    or type(observation.value) not in (float, int)
                    or not isfinite(observation.value) or observation.value < 0
                    or type(observation.sample_count) is not int
                    or observation.sample_count < 0):
                raise ValueError("Invalid SLI observation")
        if before.sample_count < min_samples or after.sample_count < min_samples:
            reasons.append("INSUFFICIENT_SAMPLES")
        if after.observed_at <= before.observed_at:
            reasons.append("INVALID_MEASUREMENT_ORDER")
        if after.observed_at - before.observed_at > max_age:
            reasons.append("STALE_BASELINE")
        if before.value <= max_acceptable_value:
            reasons.append("NO_PRE_ACTION_BREACH")
    if reasons:
        return RecoveryAssessment("UNKNOWN", tuple(reasons), "HUMAN_REVIEW_REQUIRED")
    if after.value <= max_acceptable_value:
        return RecoveryAssessment("RECOVERED", (), "NONE")
    return RecoveryAssessment("NOT_RECOVERED", ("SLI_STILL_BREACHED",), "REVIEW_ROLLBACK")
