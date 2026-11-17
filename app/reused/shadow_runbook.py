"""Deterministic, non-executing runbook selection and recovery verification plan.

Catalog entries and observations are synthetic caller-supplied inputs. This
module never approves changes, calls tools, or claims recovery occurred.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunbookCandidate:
    runbook_id: str
    version: str
    service: str
    symptom: str
    approved: bool
    rollback_defined: bool
    verification_sli: str


@dataclass(frozen=True)
class RunbookPlan:
    state: str
    reasons: tuple[str, ...]
    runbook_id: str | None
    runbook_version: str | None
    verification_sli: str | None
    verification_state: str = "NOT_MEASURED"
    authoritative: bool = False
    live_execution_authorized: bool = False


def plan_shadow_runbook(
    *,
    service: str,
    symptom: str,
    catalog: tuple[RunbookCandidate, ...],
    rca_supported: bool,
) -> RunbookPlan:
    """Choose a unique approved recipe or abstain, never execute."""
    if not service or not symptom or type(rca_supported) is not bool:
        raise ValueError("Invalid incident selection input")
    if not isinstance(catalog, tuple) or any(type(item) is not RunbookCandidate for item in catalog):
        raise ValueError("Invalid runbook catalog")
    for item in catalog:
        if (not item.runbook_id or not item.version or not item.service
                or not item.symptom or not item.verification_sli
                or type(item.approved) is not bool or type(item.rollback_defined) is not bool):
            raise ValueError("Invalid runbook entry")
    candidates = [item for item in catalog if item.service == service and item.symptom == symptom]
    reasons = []
    if not rca_supported:
        reasons.append("RCA_NOT_SUPPORTED")
    if not candidates:
        reasons.append("NO_MATCHING_RUNBOOK")
    elif len(candidates) != 1:
        reasons.append("AMBIGUOUS_RUNBOOK")
    else:
        candidate = candidates[0]
        if not candidate.approved:
            reasons.append("RUNBOOK_UNAPPROVED")
        if not candidate.rollback_defined:
            reasons.append("ROLLBACK_UNDEFINED")
    if reasons:
        return RunbookPlan("ABSTAIN", tuple(reasons), None, None, None)
    selected = candidates[0]
    return RunbookPlan(
        "REVIEW_CANDIDATE", (), selected.runbook_id, selected.version,
        selected.verification_sli,
    )
