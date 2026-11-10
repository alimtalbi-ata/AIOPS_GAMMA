from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.reused.correlation import CorrelationSignal, CorrelationPreview
from app.reused.evidence import EvidenceInput
from app.reused.correlation_evidence import CorrelationEvidencePreview, preview

TENANT = str(UUID("11111111-1111-4111-8111-111111111111"))
NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)


def request(source="otel", tenant=TENANT):
    return CorrelationEvidencePreview(
        correlation=CorrelationPreview(signals=[CorrelationSignal(
            source="otel", external_event_id="evt-1", service_name="checkout",
            environment="prod", severity="major", status="firing",
            observed_at=NOW, symptom_key="latency",
        )]),
        evidence=[EvidenceInput(
            tenant_id=tenant, incident_id="inc-1", source=source,
            external_id="evt-1", claim="latency", observed_at=NOW,
            payload={"latency_ms": 800},
        )],
    )


def test_exact_source_event_join():
    result = preview(request(), TENANT, now=NOW)
    assert len(result["groups"][0]["evidence"]) == 1
    assert result["groups"][0]["evidence_state"] == "UNVERIFIED"
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False


def test_different_source_not_linked():
    result = preview(request(source="prometheus"), TENANT, now=NOW)
    assert result["groups"][0]["evidence"] == []
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"


def test_cross_tenant_rejected():
    with pytest.raises(PermissionError):
        preview(request(tenant="other"), TENANT, now=NOW)


def test_stale_evidence_unknown():
    from datetime import timedelta
    result = preview(request(), TENANT, now=NOW + timedelta(hours=2))
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"


def test_no_evidence_remains_unknown():
    req = request()
    req.evidence = []
    result = preview(req, TENANT, now=NOW)
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["groups"][0]["evidence"] == []


def test_conflicting_duplicate_event_unknown():
    req = request()
    req.evidence.append(req.evidence[0].model_copy(update={"payload": {"latency_ms": 100}}))
    result = preview(req, TENANT, now=NOW)
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["evidence_duplicates"] == 1


def test_same_source_event_claimed_by_multiple_incidents_unknown():
    req = request()
    req.evidence.append(req.evidence[0].model_copy(update={"incident_id": "inc-2"}))
    result = preview(req, TENANT, now=NOW)
    assert len(result["groups"][0]["evidence"]) == 2
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["live_remediation_authorized"] is False


def test_conflicting_duplicate_provenance_downgrades_correlated_group():
    req = request()
    req.evidence[0].provenance = {"collector": "otel-a"}
    req.evidence.append(req.evidence[0].model_copy(
        update={"provenance": {"collector": "otel-b"}}
    ))
    result = preview(req, TENANT, now=NOW)
    assert result["evidence_duplicates"] == 1
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["groups"][0]["evidence"][0]["integrity"] == "UNVERIFIED"
    assert result["live_remediation_authorized"] is False


def test_partial_evidence_coverage_is_unknown():
    req = request()
    req.correlation.signals.append(req.correlation.signals[0].model_copy(
        update={"external_event_id": "evt-2"}
    ))
    result = preview(req, TENANT, now=NOW)
    group = result["groups"][0]
    assert group["event_count"] == 2
    assert group["evidence_covered_events"] == 1
    assert group["evidence_missing_events"] == 1
    assert group["evidence_state"] == "UNKNOWN"


def test_full_evidence_coverage_remains_unverified():
    req = request()
    req.correlation.signals.append(req.correlation.signals[0].model_copy(
        update={"external_event_id": "evt-2"}
    ))
    req.evidence.append(req.evidence[0].model_copy(
        update={"external_id": "evt-2"}
    ))
    result = preview(req, TENANT, now=NOW)
    group = result["groups"][0]
    assert group["evidence_covered_events"] == 2
    assert group["evidence_missing_events"] == 0
    assert group["evidence_state"] == "UNVERIFIED"


def test_conflicting_duplicate_alert_downgrades_evidence_group():
    req = request()
    req.correlation.signals.append(req.correlation.signals[0].model_copy(
        update={"severity": "critical", "status": "resolved"}
    ))
    result = preview(req, TENANT, now=NOW)
    assert result["deduplicated_events"] == 1
    assert result["conflicting_source_events"] == 1
    assert result["groups"][0]["conflicting_source_events"] == 1
    assert result["groups"][0]["evidence_covered_events"] == 1
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["live_remediation_authorized"] is False


def test_identical_duplicate_alert_keeps_unverified_state():
    req = request()
    req.correlation.signals.append(req.correlation.signals[0].model_copy(deep=True))
    result = preview(req, TENANT, now=NOW)
    assert result["deduplicated_events"] == 1
    assert result["conflicting_source_events"] == 0
    assert result["groups"][0]["evidence_state"] == "UNVERIFIED"


def test_duplicate_alert_with_changed_timestamp_is_conflicting():
    from datetime import timedelta
    req = request()
    req.correlation.signals.append(req.correlation.signals[0].model_copy(
        update={"observed_at": NOW + timedelta(seconds=30)}
    ))
    result = preview(req, TENANT, now=NOW)
    assert result["conflicting_source_events"] == 1
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"


def test_conflicting_duplicate_alert_is_order_independent():
    req = request()
    original = req.correlation.signals[0]
    altered = original.model_copy(update={"severity": "critical"})
    req.correlation.signals = [altered, original]
    result = preview(req, TENANT, now=NOW)
    assert result["conflicting_source_events"] == 1
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
