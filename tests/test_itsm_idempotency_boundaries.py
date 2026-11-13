"""Regression tests for the scope and stability of ITSM preview idempotency keys."""
from uuid import uuid4

from app.reused.itil import IncidentAssessment, ITSMReference
from app.reused.itsm_contract import (
    IncidentSyncPreview, PriorityMatrix, PriorityRule, plan_incident_sync,
)


def _matrix(version="v1", priority="P1"):
    levels = ("high", "medium", "low")
    return PriorityMatrix(
        policy_id="enterprise", version=version,
        rules=[PriorityRule(impact=i, urgency=u, priority=priority)
               for i in levels for u in levels],
    )


def _incident(tenant, evidence=None, ref=None):
    return IncidentAssessment(
        tenant_id=tenant, incident_id="INC-123", impact="high", urgency="high",
        evidence_refs=evidence if evidence is not None else ["trace-1"], itsm_ref=ref,
    )


def test_key_stable_across_policy_and_evidence_changes():
    tenant = uuid4()
    first = plan_incident_sync(
        IncidentSyncPreview(incident=_incident(tenant), matrix=_matrix()), tenant,
    )
    changed = plan_incident_sync(
        IncidentSyncPreview(
            incident=_incident(tenant, ["trace-2"]), matrix=_matrix("v2", "P3"),
        ), tenant,
    )
    assert first["idempotency_key"] == changed["idempotency_key"]
    assert first["priority"] != changed["priority"]


def test_key_scoped_to_tenant_operation_and_ticket():
    tenant_a, tenant_b = uuid4(), uuid4()
    create_a = plan_incident_sync(
        IncidentSyncPreview(incident=_incident(tenant_a), matrix=_matrix()), tenant_a,
    )
    create_b = plan_incident_sync(
        IncidentSyncPreview(incident=_incident(tenant_b), matrix=_matrix()), tenant_b,
    )
    ref1 = ITSMReference(system="glpi", external_id="101")
    ref2 = ITSMReference(system="glpi", external_id="102")
    enrich1 = plan_incident_sync(
        IncidentSyncPreview(
            incident=_incident(tenant_a, ref=ref1), matrix=_matrix(),
            operation="propose_enrichment", expected_itsm_ref=ref1,
        ), tenant_a,
    )
    enrich2 = plan_incident_sync(
        IncidentSyncPreview(
            incident=_incident(tenant_a, ref=ref2), matrix=_matrix(),
            operation="propose_enrichment", expected_itsm_ref=ref2,
        ), tenant_a,
    )
    keys = {result["idempotency_key"] for result in (create_a, create_b, enrich1, enrich2)}
    assert len(keys) == 4
