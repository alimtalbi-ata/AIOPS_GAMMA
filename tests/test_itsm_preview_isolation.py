"""Pure ITSM sync preview isolation regression, without vendor or database access."""
from uuid import uuid4

import pytest

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


@pytest.mark.parametrize("bad_ref", ["trace-1\nforged", "trace-1\rforged", "trace-1\tfield", "trace-1\x00", "trace-1\x7f"])
def test_itsm_preview_rejects_control_characters_in_evidence(bad_ref):
    tenant = uuid4()
    incident = IncidentAssessment(
        tenant_id=tenant, incident_id="INC-1", urgency="high", impact="high",
        evidence_refs=[bad_ref],
    )
    levels = ("high", "medium", "low")
    matrix = PriorityMatrix(
        policy_id="policy", version="v1",
        rules=[PriorityRule(impact=i, urgency=u, priority="P1")
               for i in levels for u in levels],
    )
    with pytest.raises(ValueError, match="Invalid evidence"):
        plan_incident_sync(IncidentSyncPreview(incident=incident, matrix=matrix), tenant)


@pytest.mark.parametrize("incident_id", [" ", "INC\\n2", "INC\\r2", "INC\\t2", "INC\\x00", "INC\\x7f"])
def test_incident_identifier_must_be_safe_for_sync_key(incident_id):
    tenant = uuid4()
    incident = IncidentAssessment(
        tenant_id=tenant, incident_id=incident_id, urgency="high", impact="high",
        evidence_refs=["trace-1"],
    )
    levels = ("high", "medium", "low")
    matrix = PriorityMatrix(
        policy_id="policy", version="v1",
        rules=[PriorityRule(impact=i, urgency=u, priority="P1")
               for i in levels for u in levels],
    )
    with pytest.raises(ValueError, match="Invalid incident identifier"):
        plan_incident_sync(IncidentSyncPreview(incident=incident, matrix=matrix), tenant)
