"""Synthetic AIOps autonomy decision gate. Never grants execution authority.

This pure function is for offline incident journeys and shadow-mode design.
It does not read real evidence, invoke a model, approve a runbook or execute.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShadowDecision:
    state: str
    reasons: tuple[str, ...]
    proposed_next_step: str
    authoritative: bool = False
    live_execution_authorized: bool = False


def assess_shadow_autonomy(
    *,
    evidence_source_verified: bool,
    topology_source_verified: bool,
    rca_verdict: str,
    supporting_evidence_count: int,
    contradicting_evidence_count: int,
    runbook_approved: bool,
    policy_approved: bool,
    hitl_approved: bool,
) -> ShadowDecision:
    """Explain whether a synthetic incident may proceed to human review.

    Even the strongest inputs produce a review proposal, never an execution
    permission. Unknown or contradictory evidence requires abstention.
    """
    if type(supporting_evidence_count) is not int or supporting_evidence_count < 0:
        raise ValueError("Invalid supporting evidence count")
    if type(contradicting_evidence_count) is not int or contradicting_evidence_count < 0:
        raise ValueError("Invalid contradicting evidence count")
    if rca_verdict not in ("unknown", "supported", "rejected"):
        raise ValueError("Invalid RCA verdict")
    flags = (evidence_source_verified, topology_source_verified,
             runbook_approved, policy_approved, hitl_approved)
    if any(type(flag) is not bool for flag in flags):
        raise ValueError("Invalid qualification flag")

    reasons = []
    if not evidence_source_verified:
        reasons.append("EVIDENCE_UNVERIFIED")
    if not topology_source_verified:
        reasons.append("TOPOLOGY_UNVERIFIED")
    if rca_verdict != "supported":
        reasons.append("RCA_NOT_SUPPORTED")
    if supporting_evidence_count == 0:
        reasons.append("NO_SUPPORTING_EVIDENCE")
    if contradicting_evidence_count:
        reasons.append("CONTRADICTING_EVIDENCE")
    if not runbook_approved:
        reasons.append("RUNBOOK_UNAPPROVED")
    if not policy_approved:
        reasons.append("POLICY_UNAPPROVED")
    if not hitl_approved:
        reasons.append("HITL_MISSING")

    if reasons:
        return ShadowDecision(
            state="ABSTAIN",
            reasons=tuple(reasons),
            proposed_next_step="COLLECT_EVIDENCE_OR_REQUEST_REVIEW",
        )
    return ShadowDecision(
        state="REVIEW_CANDIDATE",
        reasons=(),
        proposed_next_step="INDEPENDENT_EXECUTION_AUTHORIZATION_REQUIRED",
    )
