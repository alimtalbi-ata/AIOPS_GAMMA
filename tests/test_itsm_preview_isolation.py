"""Pure ITSM sync preview isolation regression, without vendor or database access."""
from uuid import uuid4

from app.reused.itil import IncidentAssessment
from app.reused.itsm_contract import (
    IncidentSyncPreview, PriorityMatrix, PriorityRule, plan_incident_sync,
)


def test_itsm_preview_evidence_is_independent_of_incident():
    tenant = uuid4()
    incident = IncidentAssessment(
        tenant_id=tenant, incident_id="INC-1", urgency="high", impact="high",
        evidence_refs=["trace-1"],
    )
    levels = ("high", "medium", "low")
    matrix = PriorityMatrix(
        policy_id="policy", version="v1",
        rules=[PriorityRule(impact=i, urgency=u, priority="P1")
               for i in levels for u in levels],
    )
    result = plan_incident_sync(IncidentSyncPreview(incident=incident, matrix=matrix), tenant)
    result["evidence_refs"].append("injected")
    assert incident.evidence_refs == ["trace-1"]
    assert result["live_remediation_authorized"] is False
    assert result["itsm_mutations_performed"] is False
