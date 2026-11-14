"""UC10 synthetic postmortem: deterministic review, no canonical closure."""
from datetime import datetime, timezone, timedelta
from uuid import UUID

import pytest

from app.reused.synthetic_postmortem import (
    PostmortemDraftRequest, TimelineEvent, draft_postmortem,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


def request(**changes):
    data = dict(tenant_id=TENANT, incident_id="DEMO-INC-1",
                service_name="checkout", timeline=[
                    TimelineEvent(event_id="later", occurred_at=NOW,
                                  summary="Alert correlated", evidence_ref="demo-alert"),
                    TimelineEvent(event_id="earlier",
                                  occurred_at=NOW - timedelta(minutes=5),
                                  summary="Latency observed"),
                ], rca_summary="Unverified latency hypothesis",
                impact_summary="Candidate dependency impact",
                follow_up_candidates=["Review timeout budget"])
    data.update(changes)
    return PostmortemDraftRequest(**data)


def test_postmortem_is_ordered_review_only_and_never_closes_incident():
    draft = draft_postmortem(request(), TENANT)
    assert [e["event_id"] for e in draft["timeline"]] == ["earlier", "later"]
    assert draft["timeline_state"] == "UNVERIFIED"
    assert draft["root_cause_state"] == "UNVERIFIED"
    assert draft["impact_state"] == "UNVERIFIED"
    assert all(e["source_verified"] is False for e in draft["timeline"])
    assert draft["human_review_required"] is True
    assert draft["authoritative"] is False
    assert draft["persisted"] is False
    assert draft["incident_closed"] is False
    assert draft["itsm_mutations_performed"] is False
    assert draft["live_remediation_authorized"] is False


def test_missing_facts_remain_unknown():
    draft = draft_postmortem(request(
        timeline=[], rca_summary=None, impact_summary=None), TENANT)
    assert draft["timeline_state"] == "UNKNOWN"
    assert draft["root_cause_state"] == "UNKNOWN"
    assert draft["impact_state"] == "UNKNOWN"


def test_cross_tenant_postmortem_is_rejected():
    with pytest.raises(PermissionError, match="Cross-tenant"):
        draft_postmortem(request(tenant_id=OTHER), TENANT)


def test_duplicate_timeline_identifiers_are_rejected():
    event = TimelineEvent(event_id="duplicate", occurred_at=NOW, summary="Alert")
    with pytest.raises(ValueError, match="Duplicate timeline"):
        draft_postmortem(request(timeline=[event, event]), TENANT)


def test_timeline_order_is_deterministic():
    req = request()
    reverse = request(timeline=list(reversed(req.timeline)))
    assert draft_postmortem(req, TENANT) == draft_postmortem(reverse, TENANT)
