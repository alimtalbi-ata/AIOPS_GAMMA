"""Negative journey gates for synthetic UC02→UC04→UC06→UC05.

The stages must fail closed independently; a valid prior preview does not
confer tenant authority on a subsequent stage.
"""
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.reused.correlation import CorrelationPreview, CorrelationSignal
from app.reused.correlation_evidence import CorrelationEvidencePreview, preview
from app.reused.evidence import EvidenceInput
from app.reused.synthetic_impact import ImpactPreviewRequest, preview_impact
from app.reused.investigation import InvestigationPreview, evaluate_investigation
from app.reused.itil import IncidentAssessment
from app.reused.itsm_contract import IncidentSyncPreview, PriorityMatrix, PriorityRule, plan_incident_sync
from app.reused.policy import RemediationProposal, evaluate

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


def test_cross_tenant_fails_at_every_independent_preview_boundary():
    signal = CorrelationSignal(
        source="otel", external_event_id="demo-1", service_name="checkout",
        environment="demo", severity="major", status="firing",
        observed_at=NOW, symptom_key="latency",
    )
    with pytest.raises(PermissionError, match="Cross-tenant"):
        preview(
            CorrelationEvidencePreview(
                correlation=CorrelationPreview(signals=[signal]),
                evidence=[EvidenceInput(
                    tenant_id=str(OTHER), incident_id="DEMO-INC-1",
                    source="otel", external_id="demo-1", claim="latency",
                    observed_at=NOW, payload={"latency_ms": 800},
                )],
            ), str(TENANT), now=NOW,
        )
    with pytest.raises(PermissionError, match="Cross-tenant"):
        preview_impact(
            ImpactPreviewRequest(
                tenant_id=OTHER, root_ci="CI-CHECKOUT", observed_at=NOW,
            ), TENANT, now=NOW,
        )
    with pytest.raises(PermissionError, match="Cross-tenant"):
        evaluate_investigation(
            InvestigationPreview(
                tenant_id=OTHER, incident_id="DEMO-INC-1", started_at=NOW,
            ), TENANT,
        )
    levels = ("high", "medium", "low")
    with pytest.raises(ValueError, match="Tenant mismatch"):
        plan_incident_sync(
            IncidentSyncPreview(
                incident=IncidentAssessment(
                    tenant_id=OTHER, incident_id="DEMO-INC-1",
                    urgency="high", impact="high", evidence_refs=["demo-1"],
                ),
                matrix=PriorityMatrix(
                    policy_id="demo", version="v1",
                    rules=[PriorityRule(impact=i, urgency=u, priority="P1")
                           for i in levels for u in levels],
                ),
            ), TENANT,
        )


def test_unknown_evidence_and_impact_do_not_grant_live_policy_authority():
    correlation = preview(
        CorrelationEvidencePreview(
            correlation=CorrelationPreview(signals=[CorrelationSignal(
                source="otel", external_event_id="demo-1",
                service_name="checkout", environment="demo",
                severity="major", status="firing", observed_at=NOW,
                symptom_key="latency",
            )]),
            evidence=[],
        ), str(TENANT), now=NOW,
    )
    impact = preview_impact(
        ImpactPreviewRequest(
            tenant_id=TENANT, root_ci="CI-CHECKOUT",
            observed_at=NOW, graph_complete=False,
        ), TENANT, now=NOW,
    )
    assert correlation["groups"][0]["evidence_state"] == "UNKNOWN"
    assert impact["impact_state"] == "UNKNOWN"

    # Even a caller's optimistic approval claims cannot bypass the policy gate.
    policy = evaluate(RemediationProposal(
        mode="LIVE", command="REMEDIATE", severity="P3", confidence=0.99,
        evidence_count=0, critic_validated=True, redundancy_ok=True,
        evidence_fresh=True, preconditions_verified=True, fencing_verified=True,
        human_approved=True, recipe_approved=True,
        asset_owner_verified=True, low_risk=True,
    ))
    assert policy["state"] == "UNKNOWN"
    assert policy["live_execution_authorized"] is False
