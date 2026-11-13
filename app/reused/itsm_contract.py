"""ITIL 4 ITSM integration boundary: deterministic, side-effect-free sync planning.

Enterprise ITSM remains the authority for incident/problem/change lifecycle.
These functions never call a vendor API, create a ticket or approve a change.
"""
from __future__ import annotations

from hashlib import sha256
from re import fullmatch
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
    def safe_policy_identity(self):
        for value in (self.policy_id, self.version):
            if not isinstance(value, str) or not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError("Invalid priority policy identity")
        return self

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
    if req.operation not in ("propose_create", "propose_enrichment"):
        raise ValueError("Invalid ITSM sync operation")
    # Pydantic model_copy(update=...) and mutable models can bypass construction validators.
    if any(not isinstance(value, str) or not value.strip() or
           any(ord(char) < 32 or ord(char) == 127 for char in value)
           for value in (req.matrix.policy_id, req.matrix.version)):
        raise ValueError("Invalid priority policy identity")
    # The matrix is mutable: recheck its complete mapping at the execution boundary.
    pairs = [(rule.impact, rule.urgency) for rule in req.matrix.rules]
    expected = {(impact, urgency) for impact in ("high", "medium", "low")
                for urgency in ("high", "medium", "low")}
    if len(pairs) != 9 or set(pairs) != expected:
        raise ValueError("Invalid priority matrix mapping")
    if any(not isinstance(rule.priority, str) or
           fullmatch(r"[a-zA-Z0-9_.-]{1,32}", rule.priority) is None
           for rule in req.matrix.rules):
        raise ValueError("Invalid priority matrix rule")
    if incident.tenant_id != tenant_id:
        raise ValueError("Tenant mismatch")
    if (not isinstance(incident.incident_id, str) or not incident.incident_id.strip()
            or len(incident.incident_id) > 128
            or any(ord(char) < 32 or ord(char) == 127 for char in incident.incident_id)):
        raise ValueError("Invalid incident identifier")
    # References are mutable, so validate their authority and identifier again.
    for reference in (incident.itsm_ref, req.expected_itsm_ref):
        if reference is None:
            continue
        if (not isinstance(reference, ITSMReference) or
                reference.system not in ("glpi", "servicenow", "jira_service_management", "other") or
                not isinstance(reference.external_id, str) or
                fullmatch(r"[a-zA-Z0-9_.:/-]{1,128}", reference.external_id) is None):
            raise ValueError("Invalid authoritative ITSM reference")
    if req.operation == "propose_create" and (incident.itsm_ref or req.expected_itsm_ref):
        raise ValueError("Existing ITSM reference cannot be used to propose creation")
    if req.operation == "propose_enrichment":
        if incident.itsm_ref is None or req.expected_itsm_ref != incident.itsm_ref:
            raise ValueError("Enrichment requires matching authoritative ITSM reference")
    rule = next((r for r in req.matrix.rules
                 if r.impact == incident.impact and r.urgency == incident.urgency), None)
    if not isinstance(incident.evidence_refs, list) or not incident.evidence_refs:
        raise ValueError("Incident requires evidence before ITSM sync proposal")
    if any(not isinstance(ref, str) or not ref.strip() or len(ref) > 255 or
           any(ord(char) < 32 or ord(char) == 127 for char in ref)
           for ref in incident.evidence_refs):
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
        "evidence_refs": list(incident.evidence_refs),
        "itsm_reference": incident.itsm_ref.model_dump() if incident.itsm_ref else None,
        "cmdb_state": "VERIFICATION_REQUIRED",
        "approval_state": "NOT_REQUESTED",
        "persistence_state": "NOT_PERSISTED",
        "itsm_mutations_performed": False,
        "live_remediation_authorized": False,
    }
