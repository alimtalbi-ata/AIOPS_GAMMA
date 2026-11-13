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


def test_empty_ci_id_is_rejected_instead_of_using_service_fallback():
    with pytest.raises(ValidationError):
        signal("a", ci="")


def test_absent_ci_id_still_uses_service_identity():
    absent = correlate([signal("a", ci=None)], "tenant-1")
    assert len(absent["groups"]) == 1
    assert absent["groups"][0]["ci_id"] is None
    assert absent["live_remediation_authorized"] is False


@pytest.mark.parametrize("blank_ci", [" ", "  ", "\t", "\n"])
def test_whitespace_only_ci_id_is_rejected(blank_ci):
    with pytest.raises(ValidationError):
        signal("a", ci=blank_ci)


@pytest.mark.parametrize("noncanonical_ci", [" CI-123", "CI-123 ", " CI-123 "])
def test_ci_id_with_surrounding_whitespace_is_rejected(noncanonical_ci):
    with pytest.raises(ValidationError):
        signal("a", ci=noncanonical_ci)


def test_canonical_ci_id_remains_valid():
    result = correlate([signal("a", ci="CI-123")], "tenant-1")
    assert result["groups"][0]["ci_id"] == "CI-123"


def test_correlation_grouping_is_permutation_invariant_across_time_windows():
    from itertools import permutations

    events = [
        signal("a", at=NOW),
        signal("b", at=NOW + timedelta(seconds=40)),
        signal("c", at=NOW + timedelta(seconds=80)),
        signal("d", at=NOW + timedelta(seconds=500)),
    ]
    expected = correlate(events, "tenant-1", window_seconds=300)
    assert len(expected["groups"]) == 2
    for order in permutations(events):
        assert correlate(list(order), "tenant-1", window_seconds=300) == expected


@pytest.mark.parametrize("field", [
    "source", "external_event_id", "service_name", "environment", "symptom_key",
])
@pytest.mark.parametrize("bad_value", ["  ", " padded", "padded "])
def test_alert_identity_rejects_blank_or_padded_values(field, bad_value):
    payload = signal("a").model_dump()
    payload[field] = bad_value
    with pytest.raises(ValidationError):
        CorrelationSignal.model_validate(payload)


def test_alert_identity_accepts_canonical_values():
    payload = signal("a").model_dump()
    assert CorrelationSignal.model_validate(payload).external_event_id == "a"


def test_evidence_refs_are_stable_under_signal_and_reference_permutations():
    first = signal("a").model_copy(update={"evidence_refs": ["z", "a", "z"]})
    second = signal("b").model_copy(update={"evidence_refs": ["m", "a"]})
    expected = correlate([first, second], "tenant-1")
    assert expected["groups"][0]["evidence_refs"] == ["a", "m", "z"]
    reordered_first = first.model_copy(update={"evidence_refs": ["z", "z", "a"]})
    reordered_second = second.model_copy(update={"evidence_refs": ["a", "m"]})
    assert correlate([reordered_second, reordered_first], "tenant-1") == expected

@pytest.mark.parametrize("seconds,expected_groups", [(300, 1), (301, 2)])
def test_correlation_window_boundary_is_inclusive_and_bounded(seconds, expected_groups):
    events = [
        signal("first", at=NOW),
        signal("second", at=NOW + timedelta(seconds=seconds)),
    ]
    result = correlate(events, "tenant-1", window_seconds=300)
    assert len(result["groups"]) == expected_groups
    assert sum(group["event_count"] for group in result["groups"]) == 2


def test_equivalent_timezone_offsets_produce_same_group_identity():
    from datetime import timedelta

    utc_signal = signal("same-event", at=NOW)
    offset_signal = signal(
        "same-event",
        at=NOW.astimezone(timezone(timedelta(hours=5, minutes=30))),
    )
    utc_result = correlate([utc_signal], "tenant-1")
    offset_result = correlate([offset_signal], "tenant-1")
    assert utc_result["groups"][0]["group_id"] == offset_result["groups"][0]["group_id"]
    assert utc_result["groups"][0]["first_observed_at"] == offset_result["groups"][0]["first_observed_at"]


def test_distinct_sources_with_same_external_id_are_not_deduplicated():
    result = correlate([
        signal("same-id", source="otel"),
        signal("same-id", source="prometheus"),
    ], "tenant-1")
    assert result["deduplicated_events"] == 0
    assert result["groups"][0]["event_count"] == 2
    assert result["conflicting_source_events"] == 0
