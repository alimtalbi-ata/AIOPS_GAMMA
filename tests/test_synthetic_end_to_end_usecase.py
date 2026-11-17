"""Synthetic UC02→UC04→UC06→UC05→UC10 journey; no canonical reads or writes.

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
from app.reused.shadow_autonomy import assess_shadow_autonomy
from app.reused.shadow_runbook import RunbookCandidate, plan_shadow_runbook
from app.reused.synthetic_recovery import assess_synthetic_recovery
from app.reused.synthetic_postmortem import PostmortemDraftRequest, TimelineEvent, draft_postmortem, render_postmortem_markdown

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

    # The synthetic investigation is not a trusted RCA. Autonomous planning
    # must abstain even when the supplied hypothesis references a trace.
    shadow = assess_shadow_autonomy(
        evidence_source_verified=investigation["citations_source_verified"],
        topology_source_verified=impact["canonical_cmdb_verified"],
        rca_verdict="unknown",
        supporting_evidence_count=1,
        contradicting_evidence_count=0,
        runbook_approved=False,
        policy_approved=False,
        hitl_approved=False,
    )
    assert shadow.state == "ABSTAIN"
    assert "EVIDENCE_UNVERIFIED" in shadow.reasons
    assert "TOPOLOGY_UNVERIFIED" in shadow.reasons
    assert "RCA_NOT_SUPPORTED" in shadow.reasons
    assert shadow.live_execution_authorized is False

    # UC08: the matching synthetic recipe is not actionable when RCA is
    # unknown. No post-action SLI has been measured.
    runbook = plan_shadow_runbook(
        service=group["service_name"], symptom="latency",
        catalog=(RunbookCandidate(
            runbook_id="demo-checkout-latency", version="v1",
            service="checkout", symptom="latency",
            approved=True, rollback_defined=True,
            verification_sli="checkout_request_latency_p95_ms",
        ),),
        rca_supported=investigation["supported_hypotheses"] > 0
        and investigation["unknown_hypotheses"] == 0,
    )
    assert runbook.state == "ABSTAIN"
    assert "RCA_NOT_SUPPORTED" in runbook.reasons
    assert runbook.runbook_id is None
    assert runbook.verification_state == "NOT_MEASURED"
    assert runbook.live_execution_authorized is False

    # UC09: no remediation has happened, so there are no legitimate
    # before/after observations. Recovery and rollback both stay unverified.
    recovery = assess_synthetic_recovery(
        before=None, after=None, max_acceptable_value=250.0,
    )
    assert recovery.state == "UNKNOWN"
    assert "MISSING_MEASUREMENT" in recovery.reasons
    assert recovery.rollback_proposal == "HUMAN_REVIEW_REQUIRED"
    assert recovery.rollback_executed is False
    assert recovery.live_execution_authorized is False

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

    # UC10 receives only explicitly supplied, unverified facts. It must not
    # turn an ITSM proposal into a persisted or closed incident.
    postmortem_request = PostmortemDraftRequest(
        tenant_id=TENANT, incident_id=proposal["incident_id"],
        service_name=group["service_name"],
        timeline=[TimelineEvent(
            event_id="demo-alert", occurred_at=NOW,
            summary="Synthetic latency alert", evidence_ref="demo-trace-1",
        )],
        rca_summary=None, impact_summary=None,
        follow_up_candidates=["Human review of latency hypothesis"],
    )
    postmortem = draft_postmortem(postmortem_request, TENANT)
    markdown = render_postmortem_markdown(postmortem_request, TENANT)
    assert postmortem["incident_id"] == proposal["incident_id"]
    assert postmortem["root_cause_state"] == "UNKNOWN"
    assert postmortem["impact_state"] == "UNKNOWN"
    assert postmortem["timeline_state"] == "UNVERIFIED"
    assert postmortem["incident_metrics"]["time_to_resolve_seconds"] is None
    assert postmortem["human_review_required"] is True
    assert postmortem["authoritative"] is False
    assert postmortem["persisted"] is False
    assert postmortem["incident_closed"] is False
    assert postmortem["itsm_mutations_performed"] is False
    assert postmortem["live_remediation_authorized"] is False
    assert "HUMAN REVIEW REQUIRED" in markdown
    assert "Root cause — UNKNOWN" in markdown
    assert "Impact — UNKNOWN" in markdown
    assert "durations: UNKNOWN" in markdown
