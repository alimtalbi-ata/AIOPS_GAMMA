"""ITIL 4-aligned, advisory AI SRE integration contracts.

Object names are interoperable projections, not an assertion of ITIL/AXELOS
certification. External ITSM remains the system of record for tickets,
problems, RFCs, approvals and CMDB CIs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ITSMReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: Literal["glpi", "servicenow", "jira_service_management", "other"]
    external_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:/-]+$")


class ObservedCI(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_name: str = Field(min_length=1, max_length=255)
    cmdb_ci_id: str | None = Field(default=None, max_length=255)
    discovery_source: str = Field(min_length=1, max_length=80)
    last_observed_at: datetime
    verified_against_cmdb: bool = False

    @model_validator(mode="after")
    def time_is_aware(self):
        if self.last_observed_at.tzinfo is None:
            raise ValueError("CI timestamp needs timezone")
        return self


class IncidentAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: str = Field(min_length=1, max_length=128)
    tenant_id: UUID
    urgency: Literal["high", "medium", "low", "unknown"]
    impact: Literal["high", "medium", "low", "unknown"]
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)
    affected_cis: list[ObservedCI] = Field(default_factory=list, max_length=100)
    itsm_ref: ITSMReference | None = None
    hypothesis: str | None = Field(default=None, max_length=1500)


class ProblemAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    related_incident_ids: list[str] = Field(min_length=1, max_length=100)
    suspected_root_cause: str = Field(min_length=1, max_length=2000)
    supporting_evidence_refs: list[str] = Field(default_factory=list, max_length=50)
    contradictory_evidence_refs: list[str] = Field(default_factory=list, max_length=50)
    known_error_id: str | None = Field(default=None, max_length=128)
    problem_ref: ITSMReference | None = None


class ChangeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    source_incident_id: str = Field(min_length=1, max_length=128)
    target_ci_id: str = Field(min_length=1, max_length=255)
    runbook_id: str = Field(min_length=1, max_length=255)
    runbook_version: str = Field(min_length=1, max_length=80)
    impact_summary: str = Field(min_length=1, max_length=2000)
    risk: Literal["low", "medium", "high", "unknown"]
    implementation_plan_ref: str = Field(min_length=1, max_length=255)
    rollback_plan_ref: str = Field(min_length=1, max_length=255)
    verification_plan_ref: str = Field(min_length=1, max_length=255)
    evidence_refs: list[str] = Field(min_length=1, max_length=50)
    itsm_change_ref: ITSMReference | None = None
    change_type: Literal["standard", "normal", "emergency"] = "normal"


def preview_itil_workflow(
    incident: IncidentAssessment,
    problem: ProblemAssessment | None = None,
    change: ChangeProposal | None = None,
) -> dict:
    """Create a non-authorizing workflow projection with explicit ownership."""
    tenant = incident.tenant_id
    if problem is not None and (problem.tenant_id != tenant or incident.incident_id not in problem.related_incident_ids):
        raise ValueError("Problem tenant or incident reference mismatch")
    if change is not None and (change.tenant_id != tenant or change.source_incident_id != incident.incident_id):
        raise ValueError("Change tenant or incident reference mismatch")
    verified_observations = sum(
        bool(ci.verified_against_cmdb and ci.cmdb_ci_id) for ci in incident.affected_cis
    )
    verified_ci_ids = {ci.cmdb_ci_id for ci in incident.affected_cis if ci.verified_against_cmdb and ci.cmdb_ci_id}
    if change is not None and change.target_ci_id not in verified_ci_ids:
        raise ValueError("Change target CI must have a verified CMDB binding")
    investigation_status = (
        "HYPOTHESIS_UNVERIFIED" if incident.hypothesis else "UNKNOWN"
    )
    problem_status = (
        "PROPOSED_WITH_EVIDENCE" if problem and problem.supporting_evidence_refs else
        "PROPOSED_UNVERIFIED" if problem else "NOT_PROPOSED"
    )
    change_status = (
        "DRAFT_AWAITING_ITSM_CHANGE_AUTHORITY" if change else "NOT_PROPOSED"
    )
    return {
        "schema_version": "aiops.gamma.itil4-preview.v1",
        "tenant_id": str(tenant),
        "incident": {
            "reference": incident.incident_id,
            "priority_inputs": {"urgency": incident.urgency, "impact": incident.impact},
            "priority": "UNASSIGNED_BY_ITSM",
            "itsm_reference": incident.itsm_ref.model_dump() if incident.itsm_ref else None,
            "investigation": investigation_status,
            "evidence_refs": list(incident.evidence_refs),
        },
        "service_configuration_management": {
            "observed_cis": len(incident.affected_cis),
            "verified_cis": verified_observations,
            "unverified_cis": len(incident.affected_cis) - verified_observations,
            "cmdb_is_authoritative": True,
        },
        "problem_management": {
            "status": problem_status,
            "known_error_ref": problem.known_error_id if problem else None,
            "supporting_evidence_refs": list(problem.supporting_evidence_refs) if problem else [],
            "contradictory_evidence_refs": list(problem.contradictory_evidence_refs) if problem else [],
        },
        "change_enablement": {
            "status": change_status,
            "change_type": change.change_type if change else None,
            "risk": change.risk if change else None,
            "authorization_state": "NOT_ASSESSED_BY_CHANGE_AUTHORITY",
            "approved_standard_model_verified": False,
            "itsm_reference": change.itsm_change_ref.model_dump() if change and change.itsm_change_ref else None,
        },
        "execution": {
            "state": "FORBIDDEN_IN_PREVIEW",
            "live_remediation_authorized": False,
            "itsm_mutations_performed": False,
        },
    }


class ITILPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident: IncidentAssessment
    problem: ProblemAssessment | None = None
    change: ChangeProposal | None = None
