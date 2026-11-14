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

def test_window_uses_rolling_adjacent_event_gap_not_total_group_span():
    events = [
        signal("a", at=NOW),
        signal("b", at=NOW + timedelta(seconds=250)),
        signal("c", at=NOW + timedelta(seconds=500)),
    ]
    result = correlate(events, "tenant-1", window_seconds=300)
    assert len(result["groups"]) == 1
    assert result["groups"][0]["event_count"] == 3
    assert result["groups"][0]["first_observed_at"] == NOW.isoformat()
    assert result["groups"][0]["last_observed_at"] == (NOW + timedelta(seconds=500)).isoformat()


def test_gap_beyond_window_starts_new_group_even_after_valid_chain():
    events = [
        signal("a", at=NOW),
        signal("b", at=NOW + timedelta(seconds=250)),
        signal("c", at=NOW + timedelta(seconds=551)),
    ]
    result = correlate(events, "tenant-1", window_seconds=300)
    assert len(result["groups"]) == 2
    assert [group["event_count"] for group in result["groups"]] == [2, 1]


def test_same_event_identity_is_deduplicated_only_once_per_source():
    events = [
        signal("same", source="otel"),
        signal("same", source="otel"),
        signal("same", source="prometheus"),
        signal("same", source="prometheus"),
    ]
    result = correlate(events, "tenant-1")
    assert result["source_events"] == 4
    assert result["deduplicated_events"] == 2
    assert result["groups"][0]["event_count"] == 2


def test_conflicting_duplicate_representative_is_stable_across_input_order():
    original = signal("same", severity="major", status="firing")
    changed = signal("same", severity="critical", status="resolved")
    first = correlate([original, changed], "tenant-1")
    second = correlate([changed, original], "tenant-1")
    assert first == second
    assert first["deduplicated_events"] == 1
    assert first["conflicting_source_events"] == 1
    assert first["groups"][0]["conflicting_source_events"] == 1
    assert first["groups"][0]["root_cause_state"] == "UNKNOWN"
    assert first["groups"][0]["itsm_ticket_state"] == "NOT_CREATED"
    assert first["persisted"] is False
    assert first["live_remediation_authorized"] is False

def test_ci_identity_groups_services_only_when_same_ci_is_explicit():
    events = [
        signal("a", service="checkout", ci="CI-42"),
        signal("b", service="payments", ci="CI-42"),
        signal("c", service="checkout", ci="CI-43"),
    ]
    result = correlate(events, "tenant-1")
    assert len(result["groups"]) == 2
    by_ci = {group["ci_id"]: group["event_count"] for group in result["groups"]}
    assert by_ci == {"CI-42": 2, "CI-43": 1}


def test_environment_and_symptom_are_hard_group_boundaries():
    events = [
        signal("a", service="checkout", symptom="timeout", at=NOW),
        signal("b", service="checkout", symptom="latency", at=NOW + timedelta(seconds=1)),
        signal("c", service="checkout", symptom="timeout", at=NOW + timedelta(seconds=2)).model_copy(update={"environment": "staging"}),
    ]
    result = correlate(events, "tenant-1")
    assert len(result["groups"]) == 3
    assert {group["environment"] for group in result["groups"]} == {"prod", "staging"}
    assert {group["symptom_key"] for group in result["groups"]} == {"timeout", "latency"}


def test_ci_and_service_identity_namespaces_do_not_collide():
    events = [
        signal("a", service="CI-42", ci=None),
        signal("b", service="different-service", ci="CI-42"),
    ]
    result = correlate(events, "tenant-1")
    assert len(result["groups"]) == 2
    assert {group["ci_id"] for group in result["groups"]} == {None, "CI-42"}


def test_duplicate_conflict_is_scoped_to_exact_source_identity():
    events = [
        signal("shared", source="otel", severity="major"),
        signal("shared", source="otel", severity="critical"),
        signal("shared", source="prometheus", severity="info"),
    ]
    result = correlate(events, "tenant-1")
    assert result["deduplicated_events"] == 1
    assert result["conflicting_source_events"] == 1
    assert sum(group["event_count"] for group in result["groups"]) == 2
    assert sum(group["conflicting_source_events"] for group in result["groups"]) == 1
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False


def test_mutated_signal_severity_rejected_at_direct_correlation_boundary():
    item = signal("mutated")
    item.severity = "unknown"
    with pytest.raises(ValidationError):
        correlate([item], "tenant-1")


def test_mutated_signal_timestamp_rejected_at_direct_correlation_boundary():
    item = signal("mutated")
    item.observed_at = datetime(2026, 11, 9, 10)
    with pytest.raises(ValidationError):
        correlate([item], "tenant-1")


def test_mutated_signal_identity_rejected_at_direct_correlation_boundary():
    item = signal("mutated")
    item.external_event_id = " padded "
    with pytest.raises(ValidationError):
        correlate([item], "tenant-1")


@pytest.mark.parametrize("invalid_window", [True, 300.5, "300"])
def test_direct_correlation_rejects_noninteger_window(invalid_window):
    with pytest.raises(ValueError, match="bounds"):
        correlate([signal("a")], "tenant-1", window_seconds=invalid_window)


def test_direct_correlation_rejects_missing_tenant_identity():
    with pytest.raises(ValueError, match="tenant identity"):
        correlate([signal("a")], "")


def test_conflicting_duplicate_with_different_ci_and_service_is_order_invariant():
    original = signal("same", service="checkout", ci="CI-1", severity="major")
    conflicting = signal("same", service="payments", ci="CI-2", severity="critical")
    forward = correlate([original, conflicting], "tenant-1")
    reverse = correlate([conflicting, original], "tenant-1")
    assert forward == reverse
    assert forward["source_events"] == 2
    assert forward["deduplicated_events"] == 1
    assert forward["conflicting_source_events"] == 1
    assert sum(group["event_count"] for group in forward["groups"]) == 1
    assert sum(group["conflicting_source_events"] for group in forward["groups"]) == 1
    assert all(group["root_cause_state"] == "UNKNOWN" for group in forward["groups"])
    assert forward["persisted"] is False
    assert forward["live_remediation_authorized"] is False


def test_direct_correlation_revalidates_mutated_evidence_reference_bounds():
    item = signal("mutated")
    item.evidence_refs = [f"evidence-{index}" for index in range(31)]
    with pytest.raises(ValidationError):
        correlate([item], "tenant-1")


def test_direct_correlation_revalidates_mutated_evidence_reference_types():
    item = signal("mutated")
    item.evidence_refs = ["valid", 42]
    with pytest.raises(ValidationError):
        correlate([item], "tenant-1")


@pytest.mark.parametrize("invalid_ref", [
    "", " ", " padded", "padded ", "x" * 257,
    "trace\nforged", "trace\x00forged", "trace\x7fforged", "\ud800",
])
def test_untrusted_correlation_evidence_reference_is_rejected(invalid_ref):
    payload = signal("event").model_dump()
    payload["evidence_refs"] = [invalid_ref]
    with pytest.raises(ValidationError, match="invalid correlation evidence reference"):
        CorrelationSignal.model_validate(payload)


def test_correlation_evidence_reference_boundary_and_mutation_revalidation():
    item = signal("event")
    item.evidence_refs = ["x" * 256]
    result = correlate([item], "tenant-1")
    assert result["groups"][0]["evidence_refs"] == ["x" * 256]
    item.evidence_refs = ["x" * 257]
    with pytest.raises(ValidationError, match="invalid correlation evidence reference"):
        correlate([item], "tenant-1")


@pytest.mark.parametrize("field", [
    "source", "external_event_id", "service_name", "environment", "symptom_key", "ci_id",
])
@pytest.mark.parametrize("bad_character", ["\\x00", "\\x1f", "\\x7f", "\\ud800"])
def test_correlation_identity_rejects_controls_and_surrogates(field, bad_character):
    payload = signal("safe", ci="CI-1").model_dump()
    payload[field] = "valid" + bad_character + "suffix"
    with pytest.raises(ValidationError):
        CorrelationSignal.model_validate(payload)


def test_direct_correlation_rejects_mutated_surrogate_identity():
    item = signal("safe")
    item.symptom_key = "bad\\ud800key"
    with pytest.raises(ValidationError):
        correlate([item], "tenant-1")
