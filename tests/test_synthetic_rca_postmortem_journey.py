"""UC06→UC10: RCA preview feeds only a reviewable synthetic postmortem.

The RCA evaluator resolves caller-provided references, not source authenticity.
A supported hypothesis is not an established root cause or incident closure.
"""
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.reused.investigation import (
    EvidenceRef, Hypothesis, InvestigationPreview, evaluate_investigation,
)
from app.reused.synthetic_postmortem import (
    PostmortemDraftRequest, TimelineEvent, draft_postmortem,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("verdict", ["unknown", "supported"])
def test_rca_to_postmortem_never_promotes_caller_claims_to_verified_facts(verdict):
    investigation = evaluate_investigation(
        InvestigationPreview(
            tenant_id=TENANT, incident_id="DEMO-INC-1", started_at=NOW,
            evidence=[EvidenceRef(
                ref_id="demo-trace", source="trace", observed_at=NOW,
            )],
            hypotheses=[Hypothesis(
                hypothesis_id="h1", summary="Possible upstream timeout",
                supporting_refs=["demo-trace"], verdict=verdict,
            )],
        ), TENANT,
    )
    assert investigation["citations_source_verified"] is False
    assert investigation["authoritative"] is False
    assert investigation["live_execution_authorized"] is False

    # The analyst supplies the narrative explicitly; no verified RCA is
    # inferred from 'supported' or from the existence of a citation.
    draft = draft_postmortem(
        PostmortemDraftRequest(
            tenant_id=TENANT, incident_id=investigation["incident_id"],
            service_name="checkout",
            timeline=[TimelineEvent(
                event_id="alert-1", occurred_at=NOW,
                summary="Synthetic latency alert", evidence_ref="demo-trace",
            )],
            rca_summary="Possible upstream timeout",
            impact_summary=None,
            follow_up_candidates=["Review timeout configuration"],
        ), TENANT,
    )
    assert draft["root_cause_state"] == "UNVERIFIED"
    assert draft["impact_state"] == "UNKNOWN"
    assert draft["timeline"][0]["source_verified"] is False
    assert draft["human_review_required"] is True
    assert draft["authoritative"] is False
    assert draft["persisted"] is False
    assert draft["incident_closed"] is False
    assert draft["itsm_mutations_performed"] is False
    assert draft["live_remediation_authorized"] is False


def test_rca_to_postmortem_cross_tenant_handoff_is_denied():
    evaluation = evaluate_investigation(
        InvestigationPreview(
            tenant_id=TENANT, incident_id="DEMO-INC-1", started_at=NOW,
        ), TENANT,
    )
    with pytest.raises(PermissionError, match="Cross-tenant"):
        draft_postmortem(
            PostmortemDraftRequest(
                tenant_id=OTHER, incident_id=evaluation["incident_id"],
                service_name="checkout",
            ), TENANT,
        )
