"""Conservative remediation decision gate adapted from aiops/app/policy/main.py.

Evaluation is advisory and NEVER authorizes an effect. The source's LIVE
HITL boolean is explicitly not a bound, one-use approval receipt.
"""
from typing import Literal
from pydantic import BaseModel, Field


class RemediationProposal(BaseModel):
    mode: Literal["LIVE", "DEMO", "REPLAY", "STORY"]
    command: Literal["OBSERVE", "ENRICH", "EXECUTE", "RESOLVE", "REMEDIATE", "CANCEL"]
    severity: Literal["P1", "P2", "P3", "P4", "UNKNOWN"]
    confidence: float = Field(ge=0, le=1)
    evidence_count: int = Field(ge=0)
    critic_validated: bool
    redundancy_ok: bool
    evidence_fresh: bool = False
    preconditions_verified: bool = False
    fencing_verified: bool = False
    human_approved: bool = False
    recipe_approved: bool = False
    asset_owner_verified: bool = False
    low_risk: bool = False


LIVE_EFFECTS = frozenset(("EXECUTE", "RESOLVE", "REMEDIATE", "CANCEL"))


def evaluate(proposal: RemediationProposal) -> dict:
    if not isinstance(proposal, RemediationProposal):
        raise ValueError("Invalid remediation proposal")
    # Models are mutable: an invalid mode must never fall through to SIMULATE.
    # Revalidate all fields before evaluating any advisory decision.
    proposal = RemediationProposal.model_validate(proposal.model_dump())
    def decision(state: str, action: str, reason: str) -> dict:
        return {
            "state": state,
            "decision": action,
            "reason": reason,
            "live_execution_authorized": False,
        }
    if proposal.mode == "LIVE" and proposal.severity == "P1":
        return decision("BLOCKED", "ESCALATE", "P1: autonomous action prohibited")
    if proposal.evidence_count == 0:
        return decision("UNKNOWN", "HUMAN_APPROVAL", "No supporting evidence")
    if proposal.mode != "LIVE":
        return decision("PASS", "SIMULATE", "Synthetic mode: no LIVE mutation")
    required = [
        ("critic validation", proposal.critic_validated),
        ("fresh evidence", proposal.evidence_fresh),
        ("asset owner", proposal.asset_owner_verified),
        ("authorized runbook", proposal.recipe_approved),
        ("low action risk", proposal.low_risk),
        ("preconditions", proposal.preconditions_verified),
        ("fencing", proposal.fencing_verified),
        ("redundancy", proposal.redundancy_ok),
    ]
    for label, passed in required:
        if not passed:
            return decision("BLOCKED", "HUMAN_APPROVAL", f"Missing requirement: {label}")
    if proposal.confidence < 0.90:
        return decision("BLOCKED", "HUMAN_APPROVAL", "Insufficient RCA confidence")
    if proposal.command in LIVE_EFFECTS:
        return decision(
            "BLOCKED", "HUMAN_APPROVAL",
            "A signed, expiring, one-use HITL receipt bound to the target/run/recipe "
            "and an independently verified execution gate are required",
        )
    return decision("PASS", "ALLOW_READ_ONLY", "Advisory only; no execution grant")
