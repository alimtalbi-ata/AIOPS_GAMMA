from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.main import app
from app.reused.itil import ChangeProposal, IncidentAssessment, ObservedCI, ProblemAssessment, preview_itil_workflow


TENANT = uuid4()


def incident(tenant=TENANT, verified=True):
    return IncidentAssessment(
        tenant_id=tenant, incident_id="INC-001", urgency="high", impact="medium",
        evidence_refs=["trace-1"], hypothesis="Database pressure (unverified)",
        affected_cis=[ObservedCI(service_name="checkout", cmdb_ci_id="CI-1",
                                 discovery_source="otel",
                                 last_observed_at=datetime.now(timezone.utc),
                                 verified_against_cmdb=verified)]
    )


def problem(tenant=TENANT):
    return ProblemAssessment(
        tenant_id=tenant, related_incident_ids=["INC-001"],
        suspected_root_cause="Possible connection exhaustion",
        supporting_evidence_refs=["trace-1"],
        contradictory_evidence_refs=["metric-2"],
    )


def change(tenant=TENANT):
    return ChangeProposal(
        tenant_id=tenant, source_incident_id="INC-001", target_ci_id="CI-1",
        runbook_id="rb-123", runbook_version="v2", risk="low",
        impact_summary="One checkout service", evidence_refs=["trace-1"],
        implementation_plan_ref="approved-runbook:rb-123:v2",
        rollback_plan_ref="rollback:rb-123:v2", verification_plan_ref="slo:checkout:latency",
        change_type="standard"
    )


def test_full_workflow_never_approves_change_or_execution():
    out = preview_itil_workflow(incident(), problem(), change())
    assert out["change_enablement"]["status"] == "DRAFT_AWAITING_ITSM_CHANGE_AUTHORITY"
    assert out["change_enablement"]["approved_standard_model_verified"] is False
    assert out["change_enablement"]["authorization_state"] == "NOT_ASSESSED_BY_CHANGE_AUTHORITY"
    assert out["execution"]["live_remediation_authorized"] is False
    assert not out["execution"]["itsm_mutations_performed"]
    assert out["service_configuration_management"]["verified_cis"] == 1
    assert out["problem_management"]["contradictory_evidence_refs"] == ["metric-2"]


def test_unverified_ci_cannot_seed_change_proposal():
    with pytest.raises(ValueError, match="verified CMDB"):
        preview_itil_workflow(incident(verified=False), change=change())


def test_cross_tenant_problem_denied():
    with pytest.raises(ValueError, match="tenant"):
        preview_itil_workflow(incident(), problem(tenant=uuid4()))


def test_cross_tenant_change_denied():
    with pytest.raises(ValueError, match="tenant"):
        preview_itil_workflow(incident(), change=change(tenant=uuid4()))


def test_wrong_incident_reference_denied():
    p = problem()
    p.related_incident_ids = ["INC-999"]
    with pytest.raises(ValueError):
        preview_itil_workflow(incident(), problem=p)


def test_unknown_incident_priority_is_owned_by_itsm():
    out = preview_itil_workflow(incident(verified=False))
    assert out["incident"]["priority"] == "UNASSIGNED_BY_ITSM"
    assert out["problem_management"]["status"] == "NOT_PROPOSED"


def test_naive_ci_observation_denied():
    with pytest.raises(ValidationError):
        ObservedCI(service_name="checkout", discovery_source="otel",
                   last_observed_at=datetime(2026, 11, 9, 12, 0))


def test_private_api_endpoint_fails_closed():
    response = TestClient(app).post("/api/v1/itil4/workflow/preview", json={})
    assert response.status_code in (401, 503)
