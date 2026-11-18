"""Pure synthetic risk screening; never grants operational authorization."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SyntheticRiskInput:
    criticality: str
    affected_services: int
    preconditions_verified: bool
    rollback_tested: bool
    maintenance_window_open: bool


def screen_risk(req: SyntheticRiskInput) -> dict:
    if type(req) is not SyntheticRiskInput:
        raise ValueError("Invalid risk input")
    if req.criticality not in ("low", "medium", "high", "critical"):
        raise ValueError("Invalid criticality")
    if type(req.affected_services) is not int or req.affected_services < 1:
        raise ValueError("Invalid impact scope")
    flags = (req.preconditions_verified, req.rollback_tested, req.maintenance_window_open)
    if any(type(flag) is not bool for flag in flags):
        raise ValueError("Invalid risk flags")
    reasons = []
    if req.criticality in ("high", "critical"):
        reasons.append("HIGH_CRITICALITY")
    if req.affected_services > 1:
        reasons.append("MULTI_SERVICE_IMPACT")
    if not req.preconditions_verified:
        reasons.append("PRECONDITIONS_UNVERIFIED")
    if not req.rollback_tested:
        reasons.append("ROLLBACK_UNTESTED")
    if not req.maintenance_window_open:
        reasons.append("OUTSIDE_MAINTENANCE_WINDOW")
    return {
        "state": "BLOCKED" if reasons else "REVIEW_CANDIDATE",
        "reasons": tuple(reasons),
        "origin": "CALLER_DECLARED_SYNTHETIC",
        "human_review_required": True,
        "authoritative": False,
        "live_execution_authorized": False,
    }
