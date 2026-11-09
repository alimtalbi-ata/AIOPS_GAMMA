from datetime import datetime, timedelta, timezone

from app.reused.correlation import CorrelationPreview, CorrelationSignal, correlate
from pydantic import ValidationError
import pytest


NOW = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)


def signal(event, *, service="checkout", symptom="timeout", at=NOW, severity="major", source="otel", status="firing", ci=None):
    return CorrelationSignal(
        source=source, external_event_id=event, service_name=service,
        environment="prod", symptom_key=symptom, severity=severity,
        status=status, observed_at=at, ci_id=ci,
        evidence_refs=["trace-abc"],
    )


def test_duplicate_source_event_is_removed():
    result = correlate([signal("a"), signal("a")], "tenant-1")
    assert result["deduplicated_events"] == 1
    assert len(result["groups"]) == 1
    assert result["groups"][0]["event_count"] == 1


def test_multiple_sources_same_symptom_group_and_escalate():
    result = correlate([signal("a"), signal("b", source="prometheus", severity="critical")], "tenant-1")
    assert len(result["groups"]) == 1
    assert result["groups"][0]["severity"] == "critical"
    assert result["groups"][0]["root_cause_state"] == "UNKNOWN"
    assert not result["live_remediation_authorized"]


def test_separate_service_and_time_window():
    events = [signal("a"), signal("b", service="billing"), signal("c", at=NOW+timedelta(minutes=10))]
    assert len(correlate(events, "tenant-1")["groups"]) == 3


def test_tenant_changes_group_identity():
    assert correlate([signal("a")], "tenant-1")["groups"][0]["group_id"] != correlate([signal("a")], "tenant-2")["groups"][0]["group_id"]


def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError):
        signal("a", at=datetime(2026, 11, 9, 10, 0))


def test_bounded_payload():
    with pytest.raises(ValidationError):
        CorrelationPreview(signals=[signal(str(i)) for i in range(501)])


def test_preview_never_opens_ticket_or_executes():
    result = correlate([signal("a", ci="CI-1")], "tenant-1")
    assert result["groups"][0]["itsm_ticket_state"] == "NOT_CREATED"
    assert result["groups"][0]["impact_state"] == "UNKNOWN_UNTIL_CMDB_VERIFIED"
    assert result["persisted"] is False
