"""Negative-case evidence join tests; no DB, network, VM or live actions."""
from datetime import datetime, timezone

import pytest

from app.reused.correlation import CorrelationPreview, CorrelationSignal
from app.reused.correlation_evidence import CorrelationEvidencePreview, preview
from app.reused.evidence import EvidenceInput

TENANT = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"
NOW = datetime(2026, 11, 9, 14, 35, tzinfo=timezone.utc)
OBSERVED = datetime(2026, 11, 9, 14, 32, tzinfo=timezone.utc)


def signal(event_id: str = "event-1"):
    return CorrelationSignal(
        source="synthetic", external_event_id=event_id,
        service_name="payment", environment="demo", severity="major",
        status="firing", observed_at=OBSERVED, symptom_key="timeout",
    )


def evidence(event_id: str = "event-1", *, tenant: str = TENANT,
             incident: str = "INC-1", observed_at=OBSERVED):
    return EvidenceInput(
        tenant_id=tenant, incident_id=incident,
        source="synthetic", external_id=event_id,
        claim="Synthetic event", observed_at=observed_at,
        payload={"demo": True}, provenance={"verified": False},
    )


def join(signals, evidence_items):
    return preview(
        CorrelationEvidencePreview(
            correlation=CorrelationPreview(signals=signals, window_seconds=300),
            evidence=evidence_items,
            max_age_seconds=3600,
        ),
        TENANT, now=NOW,
    )


def test_cross_tenant_evidence_fails_closed():
    with pytest.raises(PermissionError, match="Cross-tenant"):
        join([signal()], [evidence(tenant=OTHER)])


def test_unmatched_evidence_never_counts_as_complete():
    result = join([signal()], [evidence("different-event")])
    assert result["unmatched_evidence"] == 1
    assert result["evidence_join_complete"] is False
    assert result["evidence_join_consistent"] is False
    assert result["groups"][0]["evidence_missing_events"] == 1
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["live_remediation_authorized"] is False


def test_missing_evidence_never_counts_as_complete():
    result = join([signal()], [])
    assert result["evidence_join_complete"] is False
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["persisted"] is False


def test_matching_identity_is_not_provenance_verification():
    result = join([signal()], [evidence()])
    assert result["evidence_join_complete"] is True
    assert result["groups"][0]["evidence_state"] == "UNVERIFIED"
    assert result["groups"][0]["evidence"][0]["integrity"] == "UNVERIFIED"
    assert result["groups"][0]["root_cause_state"] == "UNKNOWN"
    assert result["groups"][0]["itsm_ticket_state"] == "NOT_CREATED"


def test_two_incident_claims_for_one_group_remain_unknown():
    result = join(
        [signal("event-1"), signal("event-2")],
        [evidence("event-1", incident="INC-1"),
         evidence("event-2", incident="INC-2")],
    )
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is False
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["live_remediation_authorized"] is False
