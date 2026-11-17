"""Read-only investigation evaluation contract; no tools, agents or side effects."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:/-]*$")
    source: str = Field(pattern=r"^(metric|log|trace|change|topology|code|runbook)$")
    observed_at: datetime

    @model_validator(mode="after")
    def require_utc(self):
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("Evidence timestamp must include timezone")
        return self


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hypothesis_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    summary: str = Field(min_length=1, max_length=500)
    supporting_refs: list[str] = Field(default_factory=list, max_length=30)
    contradicting_refs: list[str] = Field(default_factory=list, max_length=30)
    verdict: str = Field(pattern=r"^(unknown|supported|rejected)$")

    @model_validator(mode="after")
    def no_conflicting_refs(self):
        if set(self.supporting_refs) & set(self.contradicting_refs):
            raise ValueError("Evidence cannot support and contradict the same hypothesis")
        return self


class InvestigationPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    incident_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    started_at: datetime
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=100)
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_refs(self):
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("Investigation timestamp must include timezone")
        refs = [item.ref_id for item in self.evidence]
        if len(refs) != len(set(refs)):
            raise ValueError("Duplicate evidence reference")
        ids = [item.hypothesis_id for item in self.hypotheses]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate hypothesis identifier")
        allowed = set(refs)
        for hypothesis in self.hypotheses:
            used = hypothesis.supporting_refs + hypothesis.contradicting_refs
            if len(used) != len(set(used)):
                raise ValueError("Duplicate hypothesis evidence reference")
            if not set(used) <= allowed:
                raise ValueError("Unresolvable evidence reference")
            if hypothesis.verdict == "supported" and not hypothesis.supporting_refs:
                raise ValueError("Supported hypothesis requires supporting evidence")
        return self


def evaluate_investigation(req: InvestigationPreview, authorized_tenant: UUID) -> dict:
    if not isinstance(req, InvestigationPreview) or not isinstance(authorized_tenant, UUID):
        raise ValueError("Invalid investigation request or authorized tenant")
    # Caller-supplied Pydantic objects can be mutated after construction.
    # Revalidate the full graph (including reference integrity) at this boundary.
    req = InvestigationPreview.model_validate(req.model_dump())
    if req.tenant_id != authorized_tenant:
        raise PermissionError("Cross-tenant investigation rejected")
    count = len(req.hypotheses)
    cited = sum(bool(h.supporting_refs or h.contradicting_refs) for h in req.hypotheses)
    return {
        "tenant_id": str(authorized_tenant),
        "incident_id": req.incident_id,
        "started_at": req.started_at.isoformat(),
        "evidence_count": len(req.evidence),
        "hypothesis_count": count,
        "hypotheses_with_evidence": cited,
        "hypothesis_evidence_coverage_pct": round(100 * cited / count, 3) if count else None,
        "unknown_hypotheses": sum(h.verdict == "unknown" for h in req.hypotheses),
        "supported_hypotheses": sum(h.verdict == "supported" for h in req.hypotheses),
        "rejected_hypotheses": sum(h.verdict == "rejected" for h in req.hypotheses),
        "citation_references_resolved": True,
        "citations_source_verified": False,
        "human_adjudicated": False,
        "authoritative": False,
        "live_execution_authorized": False,
        "data_source": "caller_supplied_preview",
    }
