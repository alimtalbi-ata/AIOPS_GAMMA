"""ITIL 4 ITSM integration boundary: deterministic, side-effect-free sync planning.

Enterprise ITSM remains the authority for incident/problem/change lifecycle.
These functions never call a vendor API, create a ticket or approve a change.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.reused.itil import IncidentAssessment, ITSMReference


class PriorityRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    impact: Literal["high", "medium", "low"]
    urgency: Literal["high", "medium", "low"]
    priority: str = Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")


class PriorityMatrix(BaseModel):
    """An explicit, enterprise-owned mapping; no universal ITIL priority formula."""
    model_config = ConfigDict(extra="forbid")
    policy_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)
    rules: list[PriorityRule] = Field(min_length=9, max_length=9)

    @model_validator(mode="after")
    def complete_matrix(self):
        pairs = [(r.impact, r.urgency) for r in self.rules]
        expected = {(i, u) for i in ("high", "medium", "low")
                    for u in ("high", "medium", "low")}
        if len(set(pairs)) != 9 or set(pairs) != expected:
            raise ValueError("Priority matrix must contain each impact/urgency pair exactly once")
        return self


class IncidentSyncPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident: IncidentAssessment
    matrix: PriorityMatrix
    operation: Literal["propose_create", "propose_enrichment"] = "propose_create"
    expected_itsm_ref: ITSMReference | None = None


def plan_incident_sync(req: IncidentSyncPreview, tenant_id: UUID) -> dict:
    incident = req.incident
    if incident.tenant_id != tenant_id:
        raise ValueError("Tenant mismatch")
    if req.operation == "propose_create" and (incident.itsm_ref or req.expected_itsm_ref):
        raise ValueError("Existing ITSM reference cannot be used to propose creation")
    if req.operation == "propose_enrichment":
        if incident.itsm_ref is None or req.expected_itsm_ref != incident.itsm_ref:
            raise ValueError("Enrichment requires matching authoritative ITSM reference")
    rule = next((r for r in req.matrix.rules
                 if r.impact == incident.impact and r.urgency == incident.urgency), None)
    if not incident.evidence_refs:
        raise ValueError("Incident requires evidence before ITSM sync proposal")
    if any(not ref.strip() or len(ref) > 255 for ref in incident.evidence_refs):
        raise ValueError("Invalid evidence reference")
    # Identity of a logical proposed operation does not change with model output,
    # timestamps or enterprise priority mapping. Durable uniqueness and receipts
    # must be enforced by canonical Core/ITSM adapters in a later milestone.
    key = "|".join((str(tenant_id), incident.incident_id, req.operation,
                    incident.itsm_ref.system if incident.itsm_ref else "unbound",
                    incident.itsm_ref.external_id if incident.itsm_ref else "unbound"))
    return {
        "schema_version": "aiops.gamma.itsm-sync-preview.v1",
        "tenant_id": str(tenant_id),
        "incident_id": incident.incident_id,
        "operation": req.operation,
        "idempotency_key": sha256(key.encode()).hexdigest(),
        "priority": rule.priority if rule else "UNKNOWN",
        "priority_state": "PROPOSED_BY_ENTERPRISE_MATRIX" if rule else "UNKNOWN",
        "priority_policy_id": req.matrix.policy_id,
        "priority_policy_version": req.matrix.version,
        "evidence_refs": incident.evidence_refs,
        "itsm_reference": incident.itsm_ref.model_dump() if incident.itsm_ref else None,
        "cmdb_state": "VERIFICATION_REQUIRED",
        "approval_state": "NOT_REQUESTED",
        "persistence_state": "NOT_PERSISTED",
        "itsm_mutations_performed": False,
        "live_remediation_authorized": False,
    }
