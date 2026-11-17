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


@pytest.mark.parametrize("field,value", [
    ("incident_id", "  "),
    ("service_name", " checkout"),
    ("rca_summary", "\n"),
    ("impact_summary", "unknown\n"),
])
def test_invalid_incident_fields_rejected(field, value):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        request(**{field: value})


def test_untrusted_follow_up_text_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        request(follow_up_candidates=["Restart service\nwithout review"])


def test_post_validation_mutation_does_not_bypass_boundary():
    from pydantic import ValidationError
    req = request()
    req.incident_id = "  "
    with pytest.raises(ValidationError):
        draft_postmortem(req, TENANT)


def test_mutated_timeline_timestamp_is_revalidated():
    from pydantic import ValidationError
    req = request()
    req.timeline[0].occurred_at = datetime(2026, 11, 14, 12)
    with pytest.raises(ValidationError):
        draft_postmortem(req, TENANT)


def test_post_validation_tenant_mutation_cannot_bypass_authority():
    req = request()
    req.tenant_id = OTHER
    with pytest.raises(PermissionError, match="Cross-tenant"):
        draft_postmortem(req, TENANT)


def test_invalid_authorized_tenant_type_is_rejected():
    with pytest.raises(ValueError, match="authorized tenant"):
        draft_postmortem(request(), str(TENANT))


def test_invalid_request_type_is_rejected():
    with pytest.raises(ValueError, match="postmortem request"):
        draft_postmortem({"tenant_id": str(TENANT)}, TENANT)


@pytest.mark.parametrize("timeline", [
    [],
    [TimelineEvent(event_id="alert", occurred_at=NOW, summary="Alert fired")],
    [
        TimelineEvent(event_id="detected", occurred_at=NOW - timedelta(minutes=5),
                      summary="Detected"),
        TimelineEvent(event_id="resolved", occurred_at=NOW, summary="Resolved"),
    ],
])
def test_unverified_timeline_never_infers_sre_duration_metrics(timeline):
    draft = draft_postmortem(request(timeline=timeline), TENANT)
    metrics = draft["incident_metrics"]
    assert metrics["state"] == "UNKNOWN_UNTIL_CANONICAL_TIMESTAMPS_VERIFIED"
    assert metrics["time_to_detect_seconds"] is None
    assert metrics["time_to_acknowledge_seconds"] is None
    assert metrics["time_to_mitigate_seconds"] is None
    assert metrics["time_to_resolve_seconds"] is None
    assert draft["incident_closed"] is False


def test_markdown_export_is_deterministic_and_explicitly_non_authoritative():
    from app.reused.synthetic_postmortem import render_postmortem_markdown
    first = render_postmortem_markdown(request(), TENANT)
    second = render_postmortem_markdown(request(timeline=list(reversed(request().timeline))), TENANT)
    assert first == second
    assert "HUMAN REVIEW REQUIRED" in first
    assert "NON-AUTHORITATIVE" in first
    assert "source verified: NO" in first
    assert "durations: UNKNOWN" in first
    assert "No ITSM mutation, persistence, LIVE remediation or incident closure" in first


def test_markdown_export_escapes_untrusted_markup():
    from app.reused.synthetic_postmortem import render_postmortem_markdown
    req = request(
        timeline=[TimelineEvent(event_id="alert", occurred_at=NOW,
                                summary="**forged** <script>alert(1)</script>")],
        rca_summary="[approved](https://invalid.example)",
        follow_up_candidates=["- [x] Approved remediation"],
    )
    output = render_postmortem_markdown(req, TENANT)
    assert "**forged**" not in output
    assert "<script>" not in output
    assert "[approved](https://invalid.example)" not in output
    assert "- [x] Approved remediation" not in output
    assert "HUMAN REVIEW REQUIRED" in output


def test_markdown_export_missing_facts_remain_unknown():
    from app.reused.synthetic_postmortem import render_postmortem_markdown
    output = render_postmortem_markdown(request(
        timeline=[], rca_summary=None, impact_summary=None,
        follow_up_candidates=[],
    ), TENANT)
    assert "Timeline — UNKNOWN" in output
    assert "Root cause — UNKNOWN" in output
    assert "Impact — UNKNOWN" in output
    assert "UNKNOWN — no proposed follow-ups" in output


def test_markdown_export_rejects_cross_tenant_request():
    from app.reused.synthetic_postmortem import render_postmortem_markdown
    with pytest.raises(PermissionError, match="Cross-tenant"):
        render_postmortem_markdown(request(tenant_id=OTHER), TENANT)
