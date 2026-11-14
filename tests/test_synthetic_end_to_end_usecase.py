"""Synthetic UC02→UC04→UC06→UC05 journey; no canonical reads or writes.

This test deliberately composes pure preview boundaries. Each stage receives
explicit caller-supplied data; outputs are not trusted as authorizations.
"""
from datetime import datetime, timezone
from uuid import UUID

from app.reused.correlation import CorrelationPreview, CorrelationSignal
from app.reused.correlation_evidence import CorrelationEvidencePreview, preview
from app.reused.evidence import EvidenceInput
from app.reused.synthetic_impact import DependencyEdge, ImpactPreviewRequest, preview_impact
from app.reused.investigation import EvidenceRef, Hypothesis, InvestigationPreview, evaluate_investigation
from app.reused.itil import IncidentAssessment
from app.reused.itsm_contract import IncidentSyncPreview, PriorityMatrix, PriorityRule, plan_incident_sync

TENANT = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


def test_synthetic_incident_journey_preserves_all_authority_boundaries():
    alert = CorrelationSignal(
        source="otel", external_event_id="demo-alert-1",
        service_name="checkout", environment="demo", symptom_key="latency",
        severity="major", status="firing", observed_at=NOW, ci_id="CI-CHECKOUT",
    )
    correlation = preview(
        CorrelationEvidencePreview(
            correlation=CorrelationPreview(signals=[alert, alert.model_copy(deep=True)]),
            evidence=[EvidenceInput(
                tenant_id=str(TENANT), incident_id="DEMO-INC-1",
                source="otel", external_id="demo-alert-1",
                claim="latency", observed_at=NOW, payload={"latency_ms": 800},
            )],
        ), str(TENANT), now=NOW,
    )
    assert correlation["deduplicated_events"] == 1
    assert len(correlation["groups"]) == 1
    group = correlation["groups"][0]
    assert group["ci_id"] == "CI-CHECKOUT"
    assert group["evidence_state"] == "UNVERIFIED"
    assert correlation["live_remediation_authorized"] is False

    # The graph is caller supplied, not a read from the canonical Twin.
    impact = preview_impact(
        ImpactPreviewRequest(
            tenant_id=TENANT, root_ci=group["ci_id"], observed_at=NOW,
            graph_complete=False,
            edges=[DependencyEdge(
                upstream_ci="CI-CHECKOUT", dependent_ci="CI-PAYMENTS",
            )],
        ), TENANT, now=NOW,
    )
    assert impact["candidate_affected_cis"] == ["CI-CHECKOUT", "CI-PAYMENTS"]
    assert impact["impact_state"] == "UNKNOWN"
    assert impact["canonical_cmdb_verified"] is False

    # The RCA hypothesis is explicitly supplied and remains UNKNOWN.
    investigation = evaluate_investigation(
        InvestigationPreview(
            tenant_id=TENANT, incident_id="DEMO-INC-1", started_at=NOW,
            evidence=[EvidenceRef(
                ref_id="demo-trace-1", source="trace", observed_at=NOW,
            )],
            hypotheses=[Hypothesis(
                hypothesis_id="h-latency", summary="Latency root cause unverified",
                supporting_refs=["demo-trace-1"], verdict="unknown",
            )],
        ), TENANT,
    )
    assert investigation["unknown_hypotheses"] == 1
    assert investigation["citations_source_verified"] is False
    assert investigation["authoritative"] is False

    levels = ("high", "medium", "low")
    proposal = plan_incident_sync(
        IncidentSyncPreview(
            incident=IncidentAssessment(
                tenant_id=TENANT, incident_id="DEMO-INC-1",
                urgency="high", impact="high", evidence_refs=["demo-trace-1"],
            ),
            matrix=PriorityMatrix(
                policy_id="demo-matrix", version="v1",
                rules=[
                    PriorityRule(impact=i, urgency=u, priority="P1")
                    for i in levels for u in levels
                ],
            ),
        ), TENANT,
    )
    assert proposal["incident_id"] == investigation["incident_id"]
    assert proposal["cmdb_state"] == "VERIFICATION_REQUIRED"
    assert proposal["persistence_state"] == "NOT_PERSISTED"
    assert proposal["itsm_mutations_performed"] is False
    assert proposal["live_remediation_authorized"] is False
    assert all(stage["live_remediation_authorized"] is False for stage in (correlation, impact, proposal))
