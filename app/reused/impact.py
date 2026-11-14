"""Adapted from alimtalbi-ata/aiops app/shared/domain.py (main).

Pure decision helpers only. No live runtime, secrets, tenant claims or remediation.
"""
from dataclasses import dataclass

STAGES = (
    "INGEST", "NORMALIZE", "CORRELATE", "CMDB", "OBSERVE", "RAG",
    "DGX_ANALYST", "DGX_CRITIC", "POLICY", "HITL", "REMEDIATE",
    "VERIFY", "RECONCILE", "LEARN",
)
ALLOWED_TRANSITIONS = {
    "CREATED": frozenset(("RUNNING", "CANCELLED")),
    "RUNNING": frozenset(("WAITING", "BLOCKED", "RESOLVED", "FAILED", "CANCELLED")),
    "WAITING": frozenset(("RUNNING", "BLOCKED", "CANCELLED")),
    "BLOCKED": frozenset(("WAITING", "FAILED", "CANCELLED")),
    "RESOLVED": frozenset(),
    "FAILED": frozenset(),
    "CANCELLED": frozenset(),
}


def transition(current: str, next_status: str) -> str:
    if next_status not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise ValueError(f"illegal transition {current}->{next_status}")
    return next_status


@dataclass(frozen=True)
class ImpactEstimate:
    state: str
    score: float
    source: str = "UNVERIFIED_TOPOLOGY_ESTIMATE"
    live_remediation_authorized: bool = False


def estimate_impact(direct_impact: float, redundant_paths: int, total_paths: int) -> ImpactEstimate:
    # bool is an int subclass in Python; reject it explicitly at this boundary.
    if (not isinstance(direct_impact, (int, float))
            or isinstance(direct_impact, bool)
            or not 0.0 <= direct_impact <= 1.0):
        raise ValueError("direct_impact must be a finite number between 0 and 1")
    if (not isinstance(redundant_paths, int) or isinstance(redundant_paths, bool)
            or not isinstance(total_paths, int) or isinstance(total_paths, bool)
            or total_paths < 0 or redundant_paths < 0 or redundant_paths > total_paths):
        raise ValueError("invalid path counts")
    if total_paths == 0:
        return ImpactEstimate("UNKNOWN", 0.0)
    loss = total_paths - redundant_paths
    score = min(1.0, max(direct_impact, loss / total_paths))
    state = "OUTAGE" if score >= 0.75 else "DEGRADED" if score >= 0.25 else "NONE"
    return ImpactEstimate(state, score)
