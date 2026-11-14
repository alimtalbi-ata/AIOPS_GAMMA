"""Synthetic-only ITIL projection: mutable caller models must fail closed."""
from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.reused.itil import (
    ChangeProposal, IncidentAssessment, ObservedCI, ProblemAssessment,
    preview_itil_workflow,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


def incident():
    return IncidentAssessment(
        tenant_id=TENANT, incident_id="DEMO-INC-1",
        urgency="high", impact="medium",
        affected_cis=[ObservedCI(
            service_name="checkout", discovery_source="synthetic",
            last_observed_at=NOW, cmdb_ci_id="CI-DEMO-1",
            verified_against_cmdb=False,
        )],
    )


def test_mutated_incident_priority_rejected():
    item = incident()
    item.urgency = "critical"
    with pytest.raises(ValidationError):
        preview_itil_workflow(item)


def test_mutated_nested_ci_timestamp_rejected():
    item = incident()
    item.affected_cis[0].last_observed_at = datetime(2026, 11, 14, 12)
    with pytest.raises(ValidationError, match="CI timestamp needs timezone"):
        preview_itil_workflow(item)


def test_mutated_ci_verification_requires_identifier():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    item.affected_cis[0].cmdb_ci_id = None
    with pytest.raises(ValidationError, match="Verified CI requires CMDB identifier"):
        preview_itil_workflow(item)


def test_mutated_problem_reference_rejected():
    item = incident()
    problem = ProblemAssessment(
        tenant_id=TENANT, related_incident_ids=["DEMO-INC-1"],
        suspected_root_cause="Unknown synthetic hypothesis",
    )
    problem.related_incident_ids = []
    with pytest.raises(ValidationError):
        preview_itil_workflow(item, problem)


def test_mutated_change_risk_rejected():
    item = incident()
    change = ChangeProposal(
        tenant_id=TENANT, source_incident_id="DEMO-INC-1",
        target_ci_id="CI-DEMO-1", runbook_id="demo",
        runbook_version="v1", impact_summary="Synthetic only",
        risk="unknown", implementation_plan_ref="demo-implement",
        rollback_plan_ref="demo-rollback", verification_plan_ref="demo-verify",
        evidence_refs=["demo-evidence"],
    )
    change.risk = "critical"
    with pytest.raises(ValidationError):
        preview_itil_workflow(item, change)


@pytest.mark.parametrize("invalid", [None, {}, "incident"])
def test_invalid_incident_structure_rejected(invalid):
    with pytest.raises(ValueError, match="Invalid ITIL preview structure"):
        preview_itil_workflow(invalid)


def test_valid_unverified_ci_remains_non_authorizing():
    result = preview_itil_workflow(incident())
    assert result["service_configuration_management"]["verified_cis"] == 0
    assert result["change_enablement"]["authorization_state"] == "NOT_ASSESSED_BY_CHANGE_AUTHORITY"
    assert result["execution"]["live_remediation_authorized"] is False
    assert result["execution"]["itsm_mutations_performed"] is False


def test_mutated_problem_tenant_mismatch_rejected():
    item = incident()
    problem = ProblemAssessment(
        tenant_id=TENANT, related_incident_ids=["DEMO-INC-1"],
        suspected_root_cause="Unverified",
    )
    problem.tenant_id = OTHER
    with pytest.raises(ValueError, match="Problem tenant or incident reference mismatch"):
        preview_itil_workflow(item, problem)


def test_mutated_change_tenant_mismatch_rejected():
    item = incident()
    change = ChangeProposal(
        tenant_id=TENANT, source_incident_id="DEMO-INC-1",
        target_ci_id="CI-DEMO-1", runbook_id="demo", runbook_version="v1",
        impact_summary="Synthetic only", risk="unknown",
        implementation_plan_ref="demo-implement",
        rollback_plan_ref="demo-rollback",
        verification_plan_ref="demo-verify", evidence_refs=["demo-evidence"],
    )
    change.tenant_id = OTHER
    with pytest.raises(ValueError, match="Change tenant or incident reference mismatch"):
        preview_itil_workflow(item, change)


def test_mutated_change_target_requires_verified_binding():
    item = incident()
    change = ChangeProposal(
        tenant_id=TENANT, source_incident_id="DEMO-INC-1",
        target_ci_id="CI-DEMO-1", runbook_id="demo", runbook_version="v1",
        impact_summary="Synthetic only", risk="unknown",
        implementation_plan_ref="demo-implement",
        rollback_plan_ref="demo-rollback",
        verification_plan_ref="demo-verify", evidence_refs=["demo-evidence"],
    )
    with pytest.raises(ValueError, match="Change target CI must have a verified CMDB binding"):
        preview_itil_workflow(item, change)


@pytest.mark.parametrize("invalid", [{}, "problem", []])
def test_invalid_problem_structure_rejected(invalid):
    with pytest.raises(ValueError, match="Invalid ITIL preview structure"):
        preview_itil_workflow(incident(), problem=invalid)


@pytest.mark.parametrize("invalid", [{}, "change", []])
def test_invalid_change_structure_rejected(invalid):
    with pytest.raises(ValueError, match="Invalid ITIL preview structure"):
        preview_itil_workflow(incident(), change=invalid)
