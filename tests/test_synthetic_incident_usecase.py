"""UC02/UC03/UC05: synthetic-only alert-to-ITSM preview contract.

No HTTP client, database, vendor connector, canonical Core write or LIVE action.
This is a composition regression, not a qualified multi-tenant integration.
"""
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.reused.correlation import CorrelationPreview, CorrelationSignal
from app.reused.correlation_evidence import CorrelationEvidencePreview, preview
from app.reused.evidence import EvidenceInput
from app.reused.itil import IncidentAssessment
from app.reused.itsm_contract import (
    IncidentSyncPreview, PriorityMatrix, PriorityRule, plan_incident_sync,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OTHER_TENANT = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


def scenario(*, evidence=True, evidence_tenant=TENANT):
    signal = CorrelationSignal(
        source="otel", external_event_id="synthetic-event-1",
        service_name="synthetic-checkout", environment="demo",
        severity="major", status="firing", observed_at=NOW,
        symptom_key="latency", ci_id="DEMO-CI-1",
    )
    items = [EvidenceInput(
        tenant_id=str(evidence_tenant), incident_id="DEMO-INC-1",
        source="otel", external_id="synthetic-event-1",
        claim="latency", observed_at=NOW,
        payload={"latency_ms": 800},
    )] if evidence else []
    return CorrelationEvidencePreview(
        correlation=CorrelationPreview(signals=[signal, signal.model_copy(deep=True)]),
        evidence=items,
    )


def matrix():
    levels = ("high", "medium", "low")
    return PriorityMatrix(
        policy_id="synthetic-enterprise-policy", version="demo-v1",
        rules=[
            PriorityRule(impact=impact, urgency=urgency, priority="P1")
            for impact in levels for urgency in levels
        ],
    )


def test_synthetic_duplicate_alert_to_non_authoritative_itsm_preview():
    correlated = preview(scenario(), str(TENANT), now=NOW)
    assert correlated["deduplicated_events"] == 1
    assert len(correlated["groups"]) == 1
    group = correlated["groups"][0]
    assert group["event_count"] == 1
    assert group["evidence_covered_events"] == 1
    assert group["evidence_state"] == "UNVERIFIED"
    assert group["impact_state"] == "UNKNOWN_UNTIL_CMDB_VERIFIED"
    assert group["itsm_ticket_state"] == "NOT_CREATED"
    assert correlated["persisted"] is False
    assert correlated["live_remediation_authorized"] is False

    # Explicit synthetic incident input; a correlation group is NOT a canonical
    # incident identity, and the evidence remains unverified.
    incident = IncidentAssessment(
        tenant_id=TENANT, incident_id="DEMO-INC-1",
        urgency="high", impact="high",
        evidence_refs=["synthetic-event-1"],
    )
    request = IncidentSyncPreview(incident=incident, matrix=matrix())
    proposal = plan_incident_sync(request, TENANT)
    repeat = plan_incident_sync(request, TENANT)
    assert proposal == repeat
    assert proposal["priority"] == "P1"
    assert proposal["itsm_mutations_performed"] is False
    assert proposal["persistence_state"] == "NOT_PERSISTED"
    assert proposal["cmdb_state"] == "VERIFICATION_REQUIRED"
    assert proposal["approval_state"] == "NOT_REQUESTED"
    assert proposal["live_remediation_authorized"] is False


def test_synthetic_missing_evidence_remains_unknown():
    correlated = preview(scenario(evidence=False), str(TENANT), now=NOW)
    assert correlated["groups"][0]["evidence_state"] == "UNKNOWN"
    assert correlated["evidence_join_complete"] is False
    assert correlated["persisted"] is False


def test_synthetic_cross_tenant_evidence_denied():
    with pytest.raises(PermissionError, match="Cross-tenant"):
        preview(scenario(evidence_tenant=OTHER_TENANT), str(TENANT), now=NOW)


def test_synthetic_itsm_preview_rejects_other_tenant():
    incident = IncidentAssessment(
        tenant_id=OTHER_TENANT, incident_id="DEMO-INC-1",
        urgency="high", impact="high",
        evidence_refs=["synthetic-event-1"],
    )
    with pytest.raises(ValueError, match="Tenant mismatch"):
        plan_incident_sync(IncidentSyncPreview(incident=incident, matrix=matrix()), TENANT)


def test_mutated_evidence_tenant_rejected_at_correlation_boundary():
    req = scenario()
    req.evidence[0].tenant_id = str(OTHER_TENANT)
    with pytest.raises(PermissionError, match="Cross-tenant"):
        preview(req, str(TENANT), now=NOW)


def test_mutated_evidence_timestamp_rejected_at_correlation_boundary():
    from pydantic import ValidationError
    req = scenario()
    req.evidence[0].observed_at = datetime(2026, 11, 14, 12)
    with pytest.raises(ValidationError, match="observed_at requires timezone"):
        preview(req, str(TENANT), now=NOW)


def test_mutated_evidence_payload_limit_rejected_at_correlation_boundary():
    from pydantic import ValidationError
    req = scenario()
    req.evidence[0].payload = {"untrusted": "x" * 65537}
    with pytest.raises(ValidationError, match="payload exceeds"):
        preview(req, str(TENANT), now=NOW)


def test_mutated_evidence_freshness_bound_rejected_at_correlation_boundary():
    from pydantic import ValidationError
    req = scenario()
    req.max_age_seconds = 0
    with pytest.raises(ValidationError):
        preview(req, str(TENANT), now=NOW)


def test_mutated_itsm_incident_priority_inputs_rejected():
    from pydantic import ValidationError
    req = IncidentSyncPreview(
        incident=IncidentAssessment(
            tenant_id=TENANT, incident_id="DEMO-INC-1",
            urgency="high", impact="high", evidence_refs=["demo-trace"],
        ), matrix=matrix(),
    )
    req.incident.urgency = "critical"
    with pytest.raises(ValidationError):
        plan_incident_sync(req, TENANT)


def test_mutated_itsm_incident_tenant_denied():
    req = IncidentSyncPreview(
        incident=IncidentAssessment(
            tenant_id=TENANT, incident_id="DEMO-INC-1",
            urgency="high", impact="high", evidence_refs=["demo-trace"],
        ), matrix=matrix(),
    )
    req.incident.tenant_id = OTHER_TENANT
    with pytest.raises(ValueError, match="Tenant mismatch"):
        plan_incident_sync(req, TENANT)


def test_mutated_itsm_priority_matrix_rejected():
    from pydantic import ValidationError
    req = IncidentSyncPreview(
        incident=IncidentAssessment(
            tenant_id=TENANT, incident_id="DEMO-INC-1",
            urgency="high", impact="high", evidence_refs=["demo-trace"],
        ), matrix=matrix(),
    )
    req.matrix.rules[0].priority = "INVALID PRIORITY"
    with pytest.raises(ValidationError):
        plan_incident_sync(req, TENANT)


def test_itsm_invalid_authority_type_rejected():
    req = IncidentSyncPreview(
        incident=IncidentAssessment(
            tenant_id=TENANT, incident_id="DEMO-INC-1",
            urgency="high", impact="high", evidence_refs=["demo-trace"],
        ), matrix=matrix(),
    )
    with pytest.raises(ValueError, match="authorized tenant"):
        plan_incident_sync(req, str(TENANT))
