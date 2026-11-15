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

def test_window_is_anchored_to_first_event_not_rolling_gap():
    events = [
        signal("a", at=NOW),
        signal("b", at=NOW + timedelta(seconds=250)),
        signal("c", at=NOW + timedelta(seconds=500)),
    ]
    result = correlate(events, "tenant-1", window_seconds=300)
    assert len(result["groups"]) == 2
    assert [group["event_count"] for group in result["groups"]] == [2, 1]
    assert result["groups"][0]["first_observed_at"] == NOW.isoformat()
    assert result["groups"][0]["last_observed_at"] == (NOW + timedelta(seconds=250)).isoformat()


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

def test_shared_ci_does_not_override_service_boundary():
    events = [
        signal("a", service="checkout", ci="CI-42"),
        signal("b", service="payments", ci="CI-42"),
        signal("c", service="checkout", ci="CI-43"),
    ]
    result = correlate(events, "tenant-1")
    assert len(result["groups"]) == 3
    assert {(g["service_name"], g["ci_id"]) for g in result["groups"]} == {
        ("checkout", "CI-42"), ("payments", "CI-42"), ("checkout", "CI-43"),
    }


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
@pytest.mark.parametrize("bad_character", ["\x00", "\x1f", "\x7f", "\ud800"])
def test_correlation_identity_rejects_controls_and_surrogates(field, bad_character):
    payload = signal("safe", ci="CI-1").model_dump()
    payload[field] = "valid" + bad_character + "suffix"
    with pytest.raises(ValidationError):
        CorrelationSignal.model_validate(payload)


def test_direct_correlation_rejects_mutated_surrogate_identity():
    item = signal("safe")
    item.symptom_key = "bad\ud800key"
    with pytest.raises(ValidationError):
        correlate([item], "tenant-1")


@pytest.mark.parametrize("tenant", ["tenant\x00forged", "tenant\x7fforged", "tenant\ud800forged"])
def test_direct_correlation_rejects_control_or_surrogate_tenant(tenant):
    with pytest.raises(ValueError, match="tenant identity"):
        correlate([signal("a")], tenant)


def test_correlation_reversed_arrival_order_keeps_group_ids():
    events = [signal("a", at=NOW), signal("b", at=NOW + timedelta(seconds=30))]
    forward = correlate(events, "tenant-1")
    reverse = correlate(list(reversed(events)), "tenant-1")
    assert forward == reverse
    assert forward["groups"][0]["event_count"] == 2


def test_identical_external_ids_from_distinct_sources_remain_distinct():
    result = correlate([signal("evt", source="otel"), signal("evt", source="prometheus")], "tenant-1")
    assert result["deduplicated_events"] == 0
    assert sorted(e["source"] for e in result["groups"][0]["source_events"]) == ["otel", "prometheus"]


def test_correlation_evidence_references_are_deduplicated_across_events():
    first = signal("a").model_copy(update={"evidence_refs": ["z", "a"]})
    second = signal("b").model_copy(update={"evidence_refs": ["a", "m"]})
    result = correlate([first, second], "tenant-1")
    assert result["groups"][0]["evidence_refs"] == ["a", "m", "z"]


def test_same_service_different_symptoms_never_merge():
    result = correlate([signal("a", symptom="timeout"), signal("b", symptom="cpu")], "tenant-1")
    assert len(result["groups"]) == 2
    assert {g["symptom_key"] for g in result["groups"]} == {"timeout", "cpu"}


def test_resolved_only_correlation_group_is_not_firing():
    result = correlate([signal("a", status="resolved"), signal("b", status="resolved")], "tenant-1")
    assert result["groups"][0]["status"] == "resolved"
    assert result["live_remediation_authorized"] is False


def test_distinct_ci_identifiers_never_merge_even_with_same_service():
    result = correlate([signal("a", ci="CI-A"), signal("b", ci="CI-B")], "tenant-1")
    assert len(result["groups"]) == 2
    assert {g["ci_id"] for g in result["groups"]} == {"CI-A", "CI-B"}


def test_direct_correlation_bounds_tenant_identity_length():
    assert len(correlate([signal("a")], "t" * 128)["groups"]) == 1
    with pytest.raises(ValueError, match="tenant identity"):
        correlate([signal("a")], "t" * 129)


def test_timestamp_with_tzinfo_but_no_utc_offset_is_rejected():
    from datetime import tzinfo

    class UndefinedOffset(tzinfo):
        def utcoffset(self, dt):
            return None

        def dst(self, dt):
            return None

        def tzname(self, dt):
            return "undefined"

    with pytest.raises(ValidationError, match="valid UTC offset"):
        signal("a", at=datetime(2026, 11, 9, 10, 0, tzinfo=UndefinedOffset()))


def test_correlation_window_is_anchored_not_extended_by_event_chain():
    # Every adjacent pair is within 5 minutes, but the full chain is not.
    events = [
        signal("chain-a", at=NOW),
        signal("chain-b", at=NOW + timedelta(seconds=250)),
        signal("chain-c", at=NOW + timedelta(seconds=500)),
    ]
    result = correlate(events, "tenant-1", window_seconds=300)
    assert [group["event_count"] for group in result["groups"]] == [2, 1]
    assert all(
        datetime.fromisoformat(group["last_observed_at"])
        - datetime.fromisoformat(group["first_observed_at"])
        <= timedelta(seconds=300)
        for group in result["groups"]
    )


def test_correlation_window_boundary_is_inclusive():
    events = [
        signal("boundary-a", at=NOW),
        signal("boundary-b", at=NOW + timedelta(seconds=300)),
        signal("boundary-c", at=NOW + timedelta(seconds=301)),
    ]
    result = correlate(events, "tenant-1", window_seconds=300)
    assert [group["event_count"] for group in result["groups"]] == [2, 1]


@pytest.mark.parametrize("injected_field", [
    {"tenant_id": "other-tenant"},
    {"actor_id": "admin"},
    {"incident_id": "canonical-incident"},
    {"live_remediation_authorized": True},
])
def test_signal_rejects_forged_scope_or_authority_fields(injected_field):
    payload = signal("untrusted").model_dump()
    payload.update(injected_field)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CorrelationSignal.model_validate(payload)


def test_correlation_preview_rejects_forged_tenant_and_live_flags():
    payload = {"signals": [signal("event").model_dump()],
               "tenant_id": "other-tenant", "live_remediation_authorized": True}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CorrelationPreview.model_validate(payload)


def test_correlation_preview_accepts_explicit_valid_schema():
    preview = CorrelationPreview(signals=[signal("valid")], window_seconds=300)
    assert preview.signals[0].external_event_id == "valid"


def test_interleaved_group_keys_preserve_time_boundaries_and_order():
    events = [
        signal("a1", service="checkout", at=NOW),
        signal("b1", service="billing", at=NOW + timedelta(seconds=1)),
        signal("a2", service="checkout", at=NOW + timedelta(seconds=250)),
        signal("b2", service="billing", at=NOW + timedelta(seconds=251)),
        signal("a3", service="checkout", at=NOW + timedelta(seconds=500)),
        signal("b3", service="billing", at=NOW + timedelta(seconds=501)),
    ]
    result = correlate(events, "tenant-1", window_seconds=300)
    assert [(g["service_name"], g["event_count"]) for g in result["groups"]] == [
        ("checkout", 2), ("billing", 2), ("checkout", 1), ("billing", 1),
    ]


def test_maximum_bounded_distinct_keys_do_not_merge():
    events = [
        signal(str(i), service=f"service-{i}", at=NOW + timedelta(seconds=i))
        for i in range(500)
    ]
    result = correlate(events, "tenant-1")
    assert len(result["groups"]) == 500
    assert result["source_events"] == 500
    assert all(g["event_count"] == 1 for g in result["groups"])
    assert len({g["group_id"] for g in result["groups"]}) == 500


@pytest.mark.parametrize("statuses,expected", [
    (["firing"], "FIRING_UNVERIFIED"),
    (["resolved"], "RESOLVED_UNVERIFIED"),
    (["firing", "resolved"], "UNKNOWN"),
    (["resolved", "firing"], "UNKNOWN"),
])
def test_resolution_state_never_claims_canonical_incident_recovery(statuses, expected):
    events = [signal(str(i), status=status) for i, status in enumerate(statuses)]
    result = correlate(events, "tenant-1")
    group = result["groups"][0]
    assert group["resolution_state"] == expected
    assert group["itsm_ticket_state"] == "NOT_CREATED"
    assert result["live_remediation_authorized"] is False


def test_conflicting_duplicate_status_forces_unknown_resolution():
    events = [
        signal("same", status="firing"),
        signal("same", status="resolved"),
    ]
    result = correlate(events, "tenant-1")
    assert result["conflicting_source_events"] == 1
    assert result["groups"][0]["resolution_state"] == "UNKNOWN"


def test_large_overlapping_evidence_references_are_unique_sorted_and_private():
    events = [
        signal(str(i)).model_copy(update={
            "evidence_refs": [f"trace-{j:02d}" for j in range(i % 10, i % 10 + 30)]
        })
        for i in range(500)
    ]
    result = correlate(events, "tenant-1")
    group = result["groups"][0]
    expected = sorted({ref for event in events for ref in event.evidence_refs})
    assert group["event_count"] == 500
    assert group["evidence_refs"] == expected
    assert len(group["evidence_refs"]) == len(set(group["evidence_refs"]))
    assert "_evidence_ref_set" not in group
    assert result["live_remediation_authorized"] is False


def test_conflicting_duplicate_severity_is_unknown_regardless_of_representative():
    major = signal("same", severity="major")
    critical = signal("same", severity="critical")
    forward = correlate([major, critical], "tenant-1")
    reverse = correlate([critical, major], "tenant-1")
    assert forward == reverse
    group = forward["groups"][0]
    assert group["conflicting_source_events"] == 1
    assert group["severity_state"] == "UNKNOWN"
    assert group["root_cause_state"] == "UNKNOWN"
    assert forward["live_remediation_authorized"] is False


def test_distinct_source_severities_are_aggregated_but_not_verified():
    result = correlate([
        signal("otel-a", severity="major", source="otel"),
        signal("prom-a", severity="critical", source="prometheus"),
    ], "tenant-1")
    group = result["groups"][0]
    assert group["severity"] == "critical"
    assert group["severity_state"] == "UNVERIFIED"
    assert group["conflicting_source_events"] == 0


def test_conflicting_duplicate_never_hides_critical_severity():
    lower = signal("same", severity="info")
    higher = signal("same", severity="critical")
    for ordered in ([lower, higher], [higher, lower]):
        result = correlate(ordered, "tenant-1")
        group = result["groups"][0]
        assert group["severity"] == "critical"
        assert group["severity_state"] == "UNKNOWN"
        assert group["conflicting_source_events"] == 1
        assert result["live_remediation_authorized"] is False


def test_conflicting_duplicate_across_service_labels_keeps_conservative_severity():
    original = signal("same", service="checkout", severity="info")
    conflicting = signal("same", service="payments", severity="critical")
    forward = correlate([original, conflicting], "tenant-1")
    reverse = correlate([conflicting, original], "tenant-1")
    assert forward == reverse
    assert len(forward["groups"]) == 1
    assert forward["groups"][0]["severity"] == "critical"
    assert forward["groups"][0]["severity_state"] == "UNKNOWN"


def test_conflicting_duplicate_never_hides_reported_firing():
    firing = signal("same", status="firing")
    resolved = signal("same", status="resolved")
    for ordered in ([firing, resolved], [resolved, firing]):
        result = correlate(ordered, "tenant-1")
        group = result["groups"][0]
        assert group["status"] == "firing"
        assert group["resolution_state"] == "UNKNOWN"
        assert group["conflicting_source_events"] == 1
        assert result["live_remediation_authorized"] is False


def test_only_resolved_versions_keep_resolved_display():
    first = signal("same", status="resolved", severity="minor")
    second = signal("same", status="resolved", severity="critical")
    result = correlate([first, second], "tenant-1")
    group = result["groups"][0]
    assert group["status"] == "resolved"
    assert group["resolution_state"] == "UNKNOWN"
    assert group["severity"] == "critical"


def test_conflicting_duplicate_retains_all_evidence_references():
    first = signal("same").model_copy(update={"evidence_refs": ["trace-a", "shared"]})
    second = signal("same").model_copy(update={"evidence_refs": ["trace-b", "shared"]})
    forward = correlate([first, second], "tenant-1")
    reverse = correlate([second, first], "tenant-1")
    assert forward == reverse
    group = forward["groups"][0]
    assert group["evidence_refs"] == ["shared", "trace-a", "trace-b"]
    assert group["conflicting_source_events"] == 1
    assert group["severity_state"] == "UNKNOWN"
    assert group["resolution_state"] == "UNKNOWN"
    assert forward["live_remediation_authorized"] is False


def test_identical_duplicate_references_remain_unique():
    first = signal("same").model_copy(update={"evidence_refs": ["trace-a", "trace-b"]})
    result = correlate([first, first.model_copy(deep=True)], "tenant-1")
    assert result["groups"][0]["evidence_refs"] == ["trace-a", "trace-b"]
    assert result["conflicting_source_events"] == 0
    assert result["deduplicated_events"] == 1
