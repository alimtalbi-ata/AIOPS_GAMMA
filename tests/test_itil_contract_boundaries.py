"""Pure ITIL projection security tests; no API or database dependencies."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.reused.itil import (
    ChangeProposal, IncidentAssessment, ITSMReference, ObservedCI,
    ProblemAssessment, preview_itil_workflow,
)


def _incident(tenant, incident_id="INC-1", ci_id="CI-1", verified=True):
    return IncidentAssessment(
        incident_id=incident_id, tenant_id=tenant, urgency="unknown", impact="unknown",
        affected_cis=[ObservedCI(
            service_name="checkout", cmdb_ci_id=ci_id, discovery_source="otel",
            last_observed_at=datetime.now(timezone.utc),
            verified_against_cmdb=verified,
        )],
    )


def _change(tenant, incident_id="INC-1", ci_id="CI-1"):
    return ChangeProposal(
        tenant_id=tenant, source_incident_id=incident_id, target_ci_id=ci_id,
        runbook_id="rb", runbook_version="v1", impact_summary="test",
        risk="low", implementation_plan_ref="impl", rollback_plan_ref="rollback",
        verification_plan_ref="verify", evidence_refs=["trace-1"],
    )


@pytest.mark.parametrize("mismatch", ["tenant", "incident", "ci"])
def test_change_must_match_incident_and_verified_cmdb_binding(mismatch):
    tenant = uuid4()
    changes = {
        "tenant": {"tenant": uuid4()},
        "incident": {"incident_id": "INC-other"},
        "ci": {"ci_id": "CI-other"},
    }
    proposal = _change(tenant, **changes[mismatch])
    with pytest.raises(ValueError):
        preview_itil_workflow(_incident(tenant), change=proposal)


def test_unverified_cmdb_binding_cannot_authorize_change():
    tenant = uuid4()
    with pytest.raises(ValueError, match="verified CMDB"):
        preview_itil_workflow(_incident(tenant, verified=False), change=_change(tenant))


def test_problem_reference_must_match_incident():
    tenant = uuid4()
    problem = ProblemAssessment(
        tenant_id=tenant, related_incident_ids=["INC-other"],
        suspected_root_cause="unverified hypothesis",
    )
    with pytest.raises(ValueError, match="incident reference mismatch"):
        preview_itil_workflow(_incident(tenant), problem=problem)


def test_preview_is_non_authorizing_even_with_itsm_reference():
    tenant = uuid4()
    change = _change(tenant)
    change.itsm_change_ref = ITSMReference(system="servicenow", external_id="CHG-123")
    result = preview_itil_workflow(_incident(tenant), change=change)
    assert result["change_enablement"]["authorization_state"] == "NOT_ASSESSED_BY_CHANGE_AUTHORITY"
    assert result["change_enablement"]["approved_standard_model_verified"] is False
    assert result["execution"] == {
        "state": "FORBIDDEN_IN_PREVIEW",
        "live_remediation_authorized": False,
        "itsm_mutations_performed": False,
    }


@pytest.mark.parametrize("external_id", ["", "has spaces", "contains?query"])
def test_itsm_external_reference_rejects_unsafe_ids(external_id):
    with pytest.raises(ValidationError):
        ITSMReference(system="other", external_id=external_id)


def test_naive_ci_timestamp_rejected():
    with pytest.raises(ValidationError, match="timezone"):
        ObservedCI(
            service_name="checkout", discovery_source="otel",
            last_observed_at=datetime(2026, 11, 13),
        )
