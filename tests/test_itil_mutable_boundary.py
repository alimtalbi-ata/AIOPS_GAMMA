"""Synthetic-only ITIL projection: mutable caller models must fail closed."""
from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.reused.itil import (
    ChangeProposal, IncidentAssessment, ITSMReference, ObservedCI, ProblemAssessment,
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
        preview_itil_workflow(item, change=change)


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
        preview_itil_workflow(item, change=change)


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
        preview_itil_workflow(item, change=change)


@pytest.mark.parametrize("invalid", [{}, "problem", []])
def test_invalid_problem_structure_rejected(invalid):
    with pytest.raises(ValueError, match="Invalid ITIL preview structure"):
        preview_itil_workflow(incident(), problem=invalid)


@pytest.mark.parametrize("invalid", [{}, "change", []])
def test_invalid_change_structure_rejected(invalid):
    with pytest.raises(ValueError, match="Invalid ITIL preview structure"):
        preview_itil_workflow(incident(), change=invalid)


def test_caller_claimed_verified_ci_is_not_canonical_verification():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    result = preview_itil_workflow(item)
    cmdb = result["service_configuration_management"]
    assert cmdb["verified_cis"] == 1  # Only the caller's asserted binding.
    assert cmdb["cmdb_is_authoritative"] is True  # External source of truth.
    assert cmdb["canonical_cmdb_verified"] is False
    assert cmdb["ci_verification_source"] == "caller_supplied_preview"
    assert result["execution"]["live_remediation_authorized"] is False


def test_unverified_ci_explicitly_lacks_canonical_confirmation():
    cmdb = preview_itil_workflow(incident())["service_configuration_management"]
    assert cmdb["verified_cis"] == 0
    assert cmdb["canonical_cmdb_verified"] is False
    assert cmdb["ci_verification_source"] == "caller_supplied_preview"


def test_change_target_binding_is_not_independent_cmdb_authorization():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    change = ChangeProposal(
        tenant_id=TENANT, source_incident_id="DEMO-INC-1",
        target_ci_id="CI-DEMO-1", runbook_id="demo", runbook_version="v1",
        impact_summary="Synthetic only", risk="unknown",
        implementation_plan_ref="demo-implement",
        rollback_plan_ref="demo-rollback",
        verification_plan_ref="demo-verify", evidence_refs=["demo-evidence"],
    )
    result = preview_itil_workflow(item, change=change)
    assert result["change_enablement"]["status"] == "DRAFT_AWAITING_ITSM_CHANGE_AUTHORITY"
    assert result["change_enablement"]["target_ci_binding_source"] == "caller_supplied_preview"
    assert result["change_enablement"]["target_ci_canonical_verified"] is False
    assert result["change_enablement"]["authorization_state"] == "NOT_ASSESSED_BY_CHANGE_AUTHORITY"
    assert result["execution"]["live_remediation_authorized"] is False
    assert result["execution"]["itsm_mutations_performed"] is False


def test_absent_change_has_no_target_binding_claim():
    result = preview_itil_workflow(incident())
    assert result["change_enablement"]["target_ci_binding_source"] is None
    assert result["change_enablement"]["target_ci_canonical_verified"] is False


@pytest.mark.parametrize("caller_claims_verified", [False, True])
def test_itil_preview_never_promotes_caller_claims_to_authority(caller_claims_verified):
    item = incident()
    item.affected_cis[0].verified_against_cmdb = caller_claims_verified
    result = preview_itil_workflow(item)
    assert result["data_source"] == "caller_supplied_preview"
    assert result["authoritative"] is False
    assert result["persisted"] is False
    assert result["service_configuration_management"]["canonical_cmdb_verified"] is False
    assert result["execution"]["state"] == "FORBIDDEN_IN_PREVIEW"
    assert result["execution"]["live_remediation_authorized"] is False
    assert result["execution"]["itsm_mutations_performed"] is False


@pytest.mark.parametrize("invalid_flag", ["true", "false", 1, 0, None])
def test_mutated_ci_verification_flag_must_be_literal_boolean(invalid_flag):
    item = incident()
    item.affected_cis[0].verified_against_cmdb = invalid_flag
    with pytest.raises(ValidationError):
        preview_itil_workflow(item)


@pytest.mark.parametrize("invalid_flag", ["true", 1, None])
def test_ci_verification_flag_rejected_at_construction(invalid_flag):
    with pytest.raises(ValidationError):
        ObservedCI(
            service_name="checkout", discovery_source="synthetic",
            last_observed_at=NOW, cmdb_ci_id="CI-DEMO-1",
            verified_against_cmdb=invalid_flag,
        )


@pytest.mark.parametrize("caller_claims_verified,expected_count", [(False, 0), (True, 1)])
def test_explicit_caller_declared_ci_count(caller_claims_verified, expected_count):
    item = incident()
    item.affected_cis[0].verified_against_cmdb = caller_claims_verified
    cmdb = preview_itil_workflow(item)["service_configuration_management"]
    assert cmdb["caller_declared_verified_cis"] == expected_count
    assert cmdb["verified_cis"] == expected_count  # Legacy compatibility.
    assert cmdb["canonical_cmdb_verified"] is False


def test_duplicate_caller_verified_ci_observations_do_not_imply_unique_canonical_cis():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    item.affected_cis.append(item.affected_cis[0].model_copy(deep=True))
    cmdb = preview_itil_workflow(item)["service_configuration_management"]
    # Legacy count tracks observations, not unique verified canonical CMDB IDs.
    assert cmdb["observed_cis"] == 2
    assert cmdb["verified_cis"] == 2
    assert cmdb["caller_declared_verified_cis"] == 2
    assert cmdb["caller_declared_unique_ci_ids"] == 1
    assert cmdb["canonical_cmdb_verified"] is False
    assert cmdb["ci_verification_source"] == "caller_supplied_preview"


def test_distinct_caller_declared_ci_ids_counted_separately_without_canonical_authority():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    other_ci = item.affected_cis[0].model_copy(deep=True)
    other_ci.cmdb_ci_id = "CI-DEMO-2"
    item.affected_cis.append(other_ci)
    cmdb = preview_itil_workflow(item)["service_configuration_management"]
    assert cmdb["caller_declared_verified_cis"] == 2
    assert cmdb["caller_declared_unique_ci_ids"] == 2
    assert cmdb["canonical_cmdb_verified"] is False


def test_unverified_observation_does_not_inflate_caller_declared_unique_ci_ids():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    unverified = item.affected_cis[0].model_copy(deep=True)
    unverified.cmdb_ci_id = "CI-UNVERIFIED-2"
    unverified.verified_against_cmdb = False
    item.affected_cis.append(unverified)
    cmdb = preview_itil_workflow(item)["service_configuration_management"]
    assert cmdb["observed_cis"] == 2
    assert cmdb["verified_cis"] == 1
    assert cmdb["caller_declared_verified_cis"] == 1
    assert cmdb["caller_declared_unique_ci_ids"] == 1
    assert cmdb["unverified_cis"] == 1
    assert cmdb["canonical_cmdb_verified"] is False


@pytest.mark.parametrize("invalid_type", ["preapproved", "STANDARD", None, 1])
def test_mutated_change_type_rejected_before_any_preview(invalid_type):
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    change = ChangeProposal(
        tenant_id=TENANT, source_incident_id="DEMO-INC-1",
        target_ci_id="CI-DEMO-1", runbook_id="demo", runbook_version="v1",
        impact_summary="Synthetic only", risk="unknown",
        implementation_plan_ref="demo-implement",
        rollback_plan_ref="demo-rollback",
        verification_plan_ref="demo-verify", evidence_refs=["demo-evidence"],
    )
    change.change_type = invalid_type
    with pytest.raises(ValidationError):
        preview_itil_workflow(item, change=change)


def test_mutated_nested_itsm_reference_rejected():
    item = incident()
    item.itsm_ref = ITSMReference(system="glpi", external_id="DEMO-42")
    item.itsm_ref.external_id = "bad external id"
    with pytest.raises(ValidationError):
        preview_itil_workflow(item)


def test_mutated_nested_change_itsm_reference_rejected():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    change = ChangeProposal(
        tenant_id=TENANT, source_incident_id="DEMO-INC-1",
        target_ci_id="CI-DEMO-1", runbook_id="demo", runbook_version="v1",
        impact_summary="Synthetic only", risk="unknown",
        implementation_plan_ref="demo-implement",
        rollback_plan_ref="demo-rollback",
        verification_plan_ref="demo-verify", evidence_refs=["demo-evidence"],
        itsm_change_ref=ITSMReference(system="glpi", external_id="DEMO-CHG-42"),
    )
    change.itsm_change_ref.system = "unrecognized"
    with pytest.raises(ValidationError):
        preview_itil_workflow(item, change=change)


def test_mutated_nested_problem_itsm_reference_rejected():
    item = incident()
    problem = ProblemAssessment(
        tenant_id=TENANT, related_incident_ids=["DEMO-INC-1"],
        suspected_root_cause="Unknown synthetic hypothesis",
        problem_ref=ITSMReference(system="glpi", external_id="DEMO-PROB-42"),
    )
    problem.problem_ref.external_id = "invalid problem ref"
    with pytest.raises(ValidationError):
        preview_itil_workflow(item, problem=problem)


@pytest.mark.parametrize("invalid_id", ["   ", "DEMO\\nINC", "DEMO\\x7fINC"])
def test_mutated_incident_identifier_rejected(invalid_id):
    item = incident()
    item.incident_id = invalid_id
    with pytest.raises(ValueError, match="Invalid incident identifier"):
        preview_itil_workflow(item)


def test_model_copy_update_cannot_bypass_ci_verification_boolean_validation():
    item = incident()
    item.affected_cis[0] = item.affected_cis[0].model_copy(
        update={"verified_against_cmdb": "true"}
    )
    with pytest.raises(ValidationError):
        preview_itil_workflow(item)


def test_model_copy_update_cannot_bypass_change_type_validation():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    change = ChangeProposal(
        tenant_id=TENANT, source_incident_id="DEMO-INC-1",
        target_ci_id="CI-DEMO-1", runbook_id="demo", runbook_version="v1",
        impact_summary="Synthetic only", risk="unknown",
        implementation_plan_ref="demo-implement",
        rollback_plan_ref="demo-rollback",
        verification_plan_ref="demo-verify", evidence_refs=["demo-evidence"],
    ).model_copy(update={"change_type": "preapproved"})
    with pytest.raises(ValidationError):
        preview_itil_workflow(item, change=change)


@pytest.mark.parametrize("invalid_ci_id", [None, "", "   "])
def test_model_copy_update_cannot_claim_verified_ci_without_identifier(invalid_ci_id):
    item = incident()
    item.affected_cis[0] = item.affected_cis[0].model_copy(
        update={"verified_against_cmdb": True, "cmdb_ci_id": invalid_ci_id}
    )
    with pytest.raises(ValidationError, match="Verified CI requires CMDB identifier"):
        preview_itil_workflow(item)


def test_full_synthetic_itil_projection_never_grants_authority():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    item.itsm_ref = ITSMReference(system="glpi", external_id="DEMO-INC-42")
    problem = ProblemAssessment(
        tenant_id=TENANT, related_incident_ids=["DEMO-INC-1"],
        suspected_root_cause="Unverified synthetic hypothesis",
        supporting_evidence_refs=["DEMO-EVIDENCE-1"],
        problem_ref=ITSMReference(system="glpi", external_id="DEMO-PROB-42"),
    )
    change = ChangeProposal(
        tenant_id=TENANT, source_incident_id="DEMO-INC-1",
        target_ci_id="CI-DEMO-1", runbook_id="demo", runbook_version="v1",
        impact_summary="Synthetic only", risk="unknown",
        implementation_plan_ref="demo-implement",
        rollback_plan_ref="demo-rollback",
        verification_plan_ref="demo-verify", evidence_refs=["DEMO-EVIDENCE-1"],
        itsm_change_ref=ITSMReference(system="glpi", external_id="DEMO-CHG-42"),
    )
    result = preview_itil_workflow(item, problem=problem, change=change)
    assert result["data_source"] == "caller_supplied_preview"
    assert result["authoritative"] is False
    assert result["persisted"] is False
    assert result["service_configuration_management"]["canonical_cmdb_verified"] is False
    assert result["problem_management"]["status"] == "PROPOSED_WITH_EVIDENCE"
    assert result["change_enablement"]["status"] == "DRAFT_AWAITING_ITSM_CHANGE_AUTHORITY"
    assert result["change_enablement"]["authorization_state"] == "NOT_ASSESSED_BY_CHANGE_AUTHORITY"
    assert result["change_enablement"]["approved_standard_model_verified"] is False
    assert result["change_enablement"]["target_ci_canonical_verified"] is False
    assert result["execution"] == {
        "state": "FORBIDDEN_IN_PREVIEW",
        "live_remediation_authorized": False,
        "itsm_mutations_performed": False,
    }


def test_mutated_incident_ci_list_over_limit_rejected_before_preview():
    item = incident()
    item.affected_cis.extend(
        item.affected_cis[0].model_copy(deep=True) for _ in range(100)
    )
    assert len(item.affected_cis) == 101
    with pytest.raises(ValidationError):
        preview_itil_workflow(item)


def test_mutated_change_evidence_list_over_limit_rejected_before_preview():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    change = ChangeProposal(
        tenant_id=TENANT, source_incident_id="DEMO-INC-1",
        target_ci_id="CI-DEMO-1", runbook_id="demo", runbook_version="v1",
        impact_summary="Synthetic only", risk="unknown",
        implementation_plan_ref="demo-implement",
        rollback_plan_ref="demo-rollback",
        verification_plan_ref="demo-verify", evidence_refs=["DEMO-EVIDENCE-1"],
    )
    change.evidence_refs.extend(f"DEMO-EVIDENCE-{i}" for i in range(2, 52))
    assert len(change.evidence_refs) == 51
    with pytest.raises(ValidationError):
        preview_itil_workflow(item, change=change)


def test_itil_ci_collection_accepts_exact_limit_without_inflating_unique_ids():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    item.affected_cis.extend(
        item.affected_cis[0].model_copy(deep=True) for _ in range(99)
    )
    cmdb = preview_itil_workflow(item)["service_configuration_management"]
    assert cmdb["observed_cis"] == 100
    assert cmdb["caller_declared_verified_cis"] == 100
    assert cmdb["caller_declared_unique_ci_ids"] == 1
    assert cmdb["canonical_cmdb_verified"] is False


def test_itil_change_evidence_collection_accepts_exact_limit_without_authority():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    change = ChangeProposal(
        tenant_id=TENANT, source_incident_id="DEMO-INC-1",
        target_ci_id="CI-DEMO-1", runbook_id="demo", runbook_version="v1",
        impact_summary="Synthetic only", risk="unknown",
        implementation_plan_ref="demo-implement",
        rollback_plan_ref="demo-rollback",
        verification_plan_ref="demo-verify",
        evidence_refs=[f"DEMO-EVIDENCE-{i}" for i in range(50)],
    )
    result = preview_itil_workflow(item, change=change)
    assert result["change_enablement"]["status"] == "DRAFT_AWAITING_ITSM_CHANGE_AUTHORITY"
    assert result["change_enablement"]["authorization_state"] == "NOT_ASSESSED_BY_CHANGE_AUTHORITY"
    assert result["execution"]["live_remediation_authorized"] is False



def test_model_copy_injected_incident_authority_cannot_escape_preview():
    item = incident().model_copy(update={"canonical_authorized": True})
    result = preview_itil_workflow(item)
    assert result["authoritative"] is False
    assert result["persisted"] is False
    assert result["execution"]["live_remediation_authorized"] is False
    assert "canonical_authorized" not in result


def test_model_copy_injected_nested_ci_authority_cannot_escape_preview():
    item = incident()
    item.affected_cis[0] = item.affected_cis[0].model_copy(
        update={"canonical_cmdb_verified": True}
    )
    result = preview_itil_workflow(item)
    assert result["service_configuration_management"]["canonical_cmdb_verified"] is False
    assert result["execution"]["live_remediation_authorized"] is False


def test_model_copy_injected_change_approval_cannot_escape_preview():
    item = incident()
    item.affected_cis[0].verified_against_cmdb = True
    change = ChangeProposal(
        tenant_id=TENANT, source_incident_id="DEMO-INC-1",
        target_ci_id="CI-DEMO-1", runbook_id="demo", runbook_version="v1",
        impact_summary="Synthetic only", risk="unknown",
        implementation_plan_ref="demo-implement",
        rollback_plan_ref="demo-rollback",
        verification_plan_ref="demo-verify", evidence_refs=["DEMO-EVIDENCE-1"],
    ).model_copy(update={"approved_by_change_authority": True})
    result = preview_itil_workflow(item, change=change)
    assert result["change_enablement"]["authorization_state"] == "NOT_ASSESSED_BY_CHANGE_AUTHORITY"
    assert result["change_enablement"]["approved_standard_model_verified"] is False
    assert result["execution"]["live_remediation_authorized"] is False
    assert "approved_by_change_authority" not in result["change_enablement"]


def test_model_copy_injected_problem_approval_cannot_escape_preview():
    item = incident()
    problem = ProblemAssessment(
        tenant_id=TENANT, related_incident_ids=["DEMO-INC-1"],
        suspected_root_cause="Unverified synthetic hypothesis",
        supporting_evidence_refs=["DEMO-EVIDENCE-1"],
    ).model_copy(update={"known_error_approved": True})
    result = preview_itil_workflow(item, problem=problem)
    assert result["problem_management"]["status"] == "PROPOSED_WITH_EVIDENCE"
    assert "known_error_approved" not in result["problem_management"]
    assert result["authoritative"] is False
    assert result["execution"]["live_remediation_authorized"] is False
