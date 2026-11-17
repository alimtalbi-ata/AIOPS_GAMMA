"""Deterministic, offline RCA investigation over caller-supplied synthetic evidence.

No connectors, LLM, network, persistence, authorization, or execution.
A verdict is only a candidate for human review, never an authoritative RCA.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Evidence:
    ref: str
    tenant_id: str
    incident_id: str
    hypothesis_id: str
    stance: str  # supports | contradicts
    observed_at: datetime
    source_verified: bool = False
    source_id: str = ""  # synthetic source identity, not authenticated provenance


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    description: str


@dataclass(frozen=True)
class InvestigationInput:
    tenant_id: str
    incident_id: str
    hypotheses: tuple[Hypothesis, ...]
    evidence: tuple[Evidence, ...]
    as_of: datetime
    max_age_seconds: int = 900
    min_independent_sources: int = 2


def investigate_shadow(req: InvestigationInput) -> dict:
    """Fail closed on invalid input, abstain on ambiguity and weak evidence."""
    if type(req) is not InvestigationInput:
        raise ValueError("Invalid investigation")
    if any(type(v) is not str or not v.strip() for v in (req.tenant_id, req.incident_id)):
        raise ValueError("Missing incident identity")
    if (type(req.as_of) is not datetime or req.as_of.tzinfo is None
            or req.as_of.utcoffset() is None
            or type(req.max_age_seconds) is not int or req.max_age_seconds < 1
            or type(req.min_independent_sources) is not int
            or req.min_independent_sources < 2):
        raise ValueError("Invalid investigation policy")
    if type(req.hypotheses) is not tuple or type(req.evidence) is not tuple:
        raise ValueError("Invalid investigation collection")
    ids = set()
    for hypothesis in req.hypotheses:
        if (type(hypothesis) is not Hypothesis
                or type(hypothesis.hypothesis_id) is not str
                or not hypothesis.hypothesis_id.strip()
                or type(hypothesis.description) is not str
                or not hypothesis.description.strip()
                or hypothesis.hypothesis_id in ids):
            raise ValueError("Invalid or duplicate hypothesis")
        ids.add(hypothesis.hypothesis_id)
    seen_refs = set()
    grouped = {key: {"supports": [], "contradicts": [], "sources": set()} for key in ids}
    rejected = []
    for item in req.evidence:
        if (type(item) is not Evidence or type(item.ref) is not str
                or not item.ref.strip() or item.ref in seen_refs
                or type(item.tenant_id) is not str or type(item.incident_id) is not str
                or type(item.hypothesis_id) is not str
                or type(item.stance) is not str
                or item.stance not in ("supports", "contradicts")
                or type(item.source_verified) is not bool
                or type(item.source_id) is not str
                or type(item.observed_at) is not datetime
                or item.observed_at.tzinfo is None
                or item.observed_at.utcoffset() is None):
            raise ValueError("Invalid or duplicate evidence")
        seen_refs.add(item.ref)
        if item.tenant_id != req.tenant_id or item.incident_id != req.incident_id:
            rejected.append((item.ref, "IDENTITY_MISMATCH"))
        elif item.hypothesis_id not in ids:
            rejected.append((item.ref, "UNKNOWN_HYPOTHESIS"))
        elif not item.source_id.strip():
            rejected.append((item.ref, "MISSING_SOURCE_ID"))
        elif not item.source_verified:
            rejected.append((item.ref, "UNVERIFIED_SOURCE"))
        elif not 0 <= (req.as_of - item.observed_at).total_seconds() <= req.max_age_seconds:
            rejected.append((item.ref, "OUT_OF_WINDOW"))
        else:
            grouped[item.hypothesis_id][item.stance].append(item.ref)
            if item.stance == "supports":
                grouped[item.hypothesis_id]["sources"].add(item.source_id.strip())
    evaluations = []
    candidates = []
    for hypothesis in req.hypotheses:
        refs = grouped[hypothesis.hypothesis_id]
        reasons = []
        if len(refs["sources"]) < req.min_independent_sources:
            reasons.append("INSUFFICIENT_SUPPORT")
        if refs["contradicts"]:
            reasons.append("CONTRADICTORY_EVIDENCE")
        status = "SUPPORTED_CANDIDATE" if not reasons else "UNPROVEN"
        if not reasons:
            candidates.append(hypothesis.hypothesis_id)
        evaluations.append({
            "hypothesis_id": hypothesis.hypothesis_id,
            "status": status,
            "supporting_refs": tuple(sorted(refs["supports"])),
            "supporting_source_ids": tuple(sorted(refs["sources"])),
            "contradicting_refs": tuple(sorted(refs["contradicts"])),
            "reasons": tuple(reasons),
        })
    reasons = []
    if rejected:
        reasons.append("REJECTED_EVIDENCE_PRESENT")
    if len(candidates) != 1:
        reasons.append("AMBIGUOUS_OR_UNSUPPORTED_RCA")
    # Rejected evidence never silently disappears from the decision.
    verdict = "REVIEW_CANDIDATE" if not reasons else "ABSTAIN"
    return {
        "tenant_id": req.tenant_id,
        "incident_id": req.incident_id,
        "mode": "synthetic_shadow",
        "state": verdict,
        "selected_hypothesis_id": candidates[0] if verdict == "REVIEW_CANDIDATE" else None,
        "reasons": tuple(reasons),
        "hypotheses": tuple(evaluations),
        "rejected_evidence": tuple(sorted(rejected)),
        "authoritative": False,
        "live_execution_authorized": False,
        "tools_invoked": False,
        "itsm_mutations_performed": False,
    }
