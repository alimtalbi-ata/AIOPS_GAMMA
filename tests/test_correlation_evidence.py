from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

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


def test_conflicting_alert_order_does_not_change_group_identity():
    original = request()
    first = original.correlation.signals[0]
    alternate = first.model_copy(update={
        "severity": "critical", "status": "resolved",
        "service_name": "other-service",
    })
    original.correlation.signals = [first, alternate]
    reversed_req = request()
    reversed_req.correlation.signals = [alternate, first]
    a = preview(original, TENANT, now=NOW)
    b = preview(reversed_req, TENANT, now=NOW)
    assert a == b
    assert a["conflicting_source_events"] == 1
    assert a["groups"][0]["evidence_state"] == "UNKNOWN"


def test_three_conflicting_versions_are_permutation_invariant():
    from itertools import permutations
    req = request()
    base = req.correlation.signals[0]
    variants = [
        base,
        base.model_copy(update={"severity": "critical", "status": "resolved"}),
        base.model_copy(update={"service_name": "different-service", "environment": "stage"}),
    ]
    results = []
    for ordered in permutations(variants):
        candidate = request()
        candidate.correlation.signals = list(ordered)
        results.append(preview(candidate, TENANT, now=NOW))
    assert all(result == results[0] for result in results)
    assert results[0]["deduplicated_events"] == 2
    assert results[0]["conflicting_source_events"] == 1
    assert results[0]["groups"][0]["evidence_state"] == "UNKNOWN"


def test_unmatched_evidence_is_reported_not_silently_dropped():
    req = request()
    req.evidence.append(req.evidence[0].model_copy(
        update={"external_id": "unrelated-event"}
    ))
    result = preview(req, TENANT, now=NOW)
    assert result["unmatched_evidence"] == 1
    assert result["evidence_join_complete"] is False
    assert result["groups"][0]["evidence_covered_events"] == 1
    assert result["groups"][0]["evidence_state"] == "UNVERIFIED"
    assert result["persisted"] is False


def test_all_evidence_matched_is_complete():
    result = preview(request(), TENANT, now=NOW)
    assert result["unmatched_evidence"] == 0
    assert result["evidence_join_complete"] is True


def test_unmatched_duplicate_count_is_not_double_counted():
    req = request()
    unrelated = req.evidence[0].model_copy(update={"external_id": "other"})
    req.evidence.extend([unrelated, unrelated.model_copy(deep=True)])
    result = preview(req, TENANT, now=NOW)
    assert result["evidence_duplicates"] == 1
    assert result["unmatched_evidence"] == 1
    assert result["evidence_join_complete"] is False


def test_join_not_complete_when_alert_has_no_evidence():
    req = request()
    req.evidence = []
    result = preview(req, TENANT, now=NOW)
    assert result["unmatched_evidence"] == 0
    assert result["groups"][0]["evidence_missing_events"] == 1
    assert result["evidence_join_complete"] is False


def test_join_not_complete_when_one_of_two_alerts_lacks_evidence():
    req = request()
    req.correlation.signals.append(req.correlation.signals[0].model_copy(
        update={"external_event_id": "evt-2"}
    ))
    result = preview(req, TENANT, now=NOW)
    assert result["unmatched_evidence"] == 0
    assert result["groups"][0]["evidence_missing_events"] == 1
    assert result["evidence_join_complete"] is False


def test_join_complete_with_full_bidirectional_coverage():
    req = request()
    req.correlation.signals.append(req.correlation.signals[0].model_copy(
        update={"external_event_id": "evt-2"}
    ))
    req.evidence.append(req.evidence[0].model_copy(
        update={"external_id": "evt-2"}
    ))
    result = preview(req, TENANT, now=NOW)
    assert result["unmatched_evidence"] == 0
    assert result["groups"][0]["evidence_missing_events"] == 0
    assert result["evidence_join_complete"] is True


def test_complete_coverage_with_conflicting_alert_is_not_consistent():
    req = request()
    req.correlation.signals.append(req.correlation.signals[0].model_copy(
        update={"severity": "critical"}
    ))
    result = preview(req, TENANT, now=NOW)
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is False
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"


def test_complete_coverage_with_stale_evidence_is_not_consistent():
    from datetime import timedelta
    result = preview(request(), TENANT, now=NOW + timedelta(hours=2))
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is False


def test_complete_coverage_with_no_conflicts_is_consistent():
    result = preview(request(), TENANT, now=NOW)
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is True
    assert result["live_remediation_authorized"] is False


def test_group_ids_do_not_collide_when_identity_contains_separator():
    from app.reused.correlation import correlate
    base = request().correlation.signals[0]
    a = base.model_copy(update={
        "environment": "prod|checkout",
        "service_name": "payments",
        "external_event_id": "one",
    })
    b = base.model_copy(update={
        "environment": "prod",
        "service_name": "checkout|payments",
        "external_event_id": "two",
    })
    result = correlate([a, b], TENANT)
    assert len(result["groups"]) == 2
    assert result["groups"][0]["group_id"] != result["groups"][1]["group_id"]


def test_group_id_is_stable_for_same_structured_identity():
    from app.reused.correlation import correlate
    signal = request().correlation.signals[0]
    a = correlate([signal], TENANT)
    b = correlate([signal.model_copy(deep=True)], TENANT)
    assert a["groups"][0]["group_id"] == b["groups"][0]["group_id"]


def test_ci_identifier_does_not_alias_service_name():
    from app.reused.correlation import correlate
    base = request().correlation.signals[0]
    ci = base.model_copy(update={
        "external_event_id": "ci-alert", "ci_id": "checkout",
        "service_name": "another-service",
    })
    service = base.model_copy(update={
        "external_event_id": "service-alert", "ci_id": None,
        "service_name": "checkout",
    })
    result = correlate([ci, service], TENANT)
    assert len(result["groups"]) == 2
    assert len({group["group_id"] for group in result["groups"]}) == 2


def test_same_ci_identifier_groups_alerts_from_different_service_labels():
    from app.reused.correlation import correlate
    base = request().correlation.signals[0]
    a = base.model_copy(update={
        "external_event_id": "a", "ci_id": "ci-123",
        "service_name": "checkout",
    })
    b = base.model_copy(update={
        "external_event_id": "b", "ci_id": "ci-123",
        "service_name": "checkout-v2",
    })
    result = correlate([a, b], TENANT)
    assert len(result["groups"]) == 1
    assert result["groups"][0]["event_count"] == 2


def test_conflicting_evidence_is_order_independent():
    base = request()
    original = base.evidence[0]
    conflicting = original.model_copy(update={
        "payload": {"latency_ms": 100}, "provenance": {"collector": "other"},
    })
    a = request()
    a.evidence = [original, conflicting]
    b = request()
    b.evidence = [conflicting, original]
    first = preview(a, TENANT, now=NOW)
    second = preview(b, TENANT, now=NOW)
    assert first == second
    assert first["evidence_duplicates"] == 1
    assert first["evidence_join_consistent"] is False
    assert first["groups"][0]["evidence_state"] == "UNKNOWN"


def test_evidence_order_independence_across_incident_claims():
    base = request()
    first = base.evidence[0]
    second = first.model_copy(update={"incident_id": "inc-2"})
    a = request()
    a.evidence = [first, second]
    b = request()
    b.evidence = [second, first]
    result_a = preview(a, TENANT, now=NOW)
    result_b = preview(b, TENANT, now=NOW)
    assert result_a == result_b
    assert result_a["groups"][0]["evidence_state"] == "UNKNOWN"


def test_three_evidence_versions_all_permutations_are_identical():
    from itertools import permutations
    req = request()
    base = req.evidence[0]
    variants = [
        base,
        base.model_copy(update={"payload": {"latency_ms": 100}}),
        base.model_copy(update={"provenance": {"collector": "other"}}),
    ]
    outputs = []
    for ordered in permutations(variants):
        candidate = request()
        candidate.evidence = list(ordered)
        outputs.append(preview(candidate, TENANT, now=NOW))
    assert all(output == outputs[0] for output in outputs)
    assert outputs[0]["evidence_duplicates"] == 2
    assert outputs[0]["evidence_join_consistent"] is False
    assert outputs[0]["groups"][0]["evidence_state"] == "UNKNOWN"

def test_tenant_rejection_happens_before_correlation(monkeypatch):
    import app.reused.correlation_evidence as join_module

    called = []
    monkeypatch.setattr(join_module, "correlate", lambda *args, **kwargs: called.append(True))
    with pytest.raises(PermissionError):
        preview(request(tenant="other"), TENANT, now=NOW)
    assert called == []


def test_consistent_join_never_promotes_evidence_authenticity():
    result = preview(request(), TENANT, now=NOW)
    group = result["groups"][0]
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is True
    assert group["evidence_state"] == "UNVERIFIED"
    assert group["evidence"][0]["integrity"] == "UNVERIFIED"
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False

def test_multi_group_join_matches_exact_source_event_only():
    req = request()
    first = req.correlation.signals[0]
    second = first.model_copy(update={
        "external_event_id": "evt-2",
        "symptom_key": "database-errors",
    })
    req.correlation.signals = [first, second]
    req.evidence.append(req.evidence[0].model_copy(update={
        "external_id": "evt-2",
        "claim": "database errors",
        "payload": {"error_rate": 0.2},
    }))
    result = preview(req, TENANT, now=NOW)
    assert len(result["groups"]) == 2
    by_symptom = {group["symptom_key"]: group for group in result["groups"]}
    assert [item["external_id"] for item in by_symptom["latency"]["evidence"]] == ["evt-1"]
    assert [item["external_id"] for item in by_symptom["database-errors"]["evidence"]] == ["evt-2"]
    assert all(group["evidence_state"] == "UNVERIFIED" for group in result["groups"])
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is True
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False


def test_same_external_id_from_wrong_source_never_cross_links_groups():
    req = request()
    req.evidence[0].source = "prometheus"
    result = preview(req, TENANT, now=NOW)
    assert result["groups"][0]["evidence"] == []
    assert result["groups"][0]["evidence_missing_events"] == 1
    assert result["unmatched_evidence"] == 1
    assert result["evidence_join_complete"] is False
    assert result["evidence_join_consistent"] is False


def test_future_evidence_is_covered_but_not_consistent():
    from datetime import timedelta

    req = request()
    req.evidence[0].observed_at = NOW + timedelta(seconds=1)
    result = preview(req, TENANT, now=NOW)
    assert result["groups"][0]["evidence_covered_events"] == 1
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is False
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False

def test_same_source_event_claimed_by_two_incidents_is_not_deduplicated():
    req = request()
    first = req.evidence[0]
    second = first.model_copy(update={"incident_id": "inc-2"})
    req.evidence = [first, second]
    result = preview(req, TENANT, now=NOW)
    assert result["evidence_duplicates"] == 0
    assert len(result["groups"][0]["evidence"]) == 2
    assert {item["incident_id"] for item in result["groups"][0]["evidence"]} == {"inc-1", "inc-2"}
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is False
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False


def test_multi_incident_claim_order_does_not_change_join_result():
    req = request()
    first = req.evidence[0]
    second = first.model_copy(update={"incident_id": "inc-2"})
    forward = request()
    forward.evidence = [first, second]
    reverse = request()
    reverse.evidence = [second, first]
    result_forward = preview(forward, TENANT, now=NOW)
    result_reverse = preview(reverse, TENANT, now=NOW)
    assert result_forward == result_reverse
    assert result_forward["groups"][0]["evidence_state"] == "UNKNOWN"


def test_stale_evidence_is_identity_covered_but_never_consistent():
    from datetime import timedelta

    result = preview(request(), TENANT, now=NOW + timedelta(hours=2))
    group = result["groups"][0]
    assert group["evidence_covered_events"] == 1
    assert group["evidence_missing_events"] == 0
    assert group["evidence_state"] == "UNKNOWN"
    assert result["unmatched_evidence"] == 0
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is False

def test_mixed_tenant_evidence_rejected_before_correlation_and_normalization(monkeypatch):
    import app.reused.correlation_evidence as join_module

    calls = {"correlate": 0, "normalize": 0}

    def forbidden_correlate(*args, **kwargs):
        calls["correlate"] += 1
        raise AssertionError("correlation must not run for mixed-tenant evidence")

    def forbidden_normalize(*args, **kwargs):
        calls["normalize"] += 1
        raise AssertionError("normalization must not run for mixed-tenant evidence")

    monkeypatch.setattr(join_module, "correlate", forbidden_correlate)
    monkeypatch.setattr(join_module, "normalize", forbidden_normalize)

    req = request()
    req.evidence.append(req.evidence[0].model_copy(update={"tenant_id": "tenant-b"}))
    with pytest.raises(PermissionError, match="Cross-tenant evidence rejected"):
        preview(req, TENANT, now=NOW)
    assert calls == {"correlate": 0, "normalize": 0}


def test_all_evidence_for_another_tenant_is_rejected_before_processing(monkeypatch):
    import app.reused.correlation_evidence as join_module

    calls = []
    monkeypatch.setattr(join_module, "correlate", lambda *a, **k: calls.append("correlate"))
    monkeypatch.setattr(join_module, "normalize", lambda *a, **k: calls.append("normalize"))

    req = request(tenant="tenant-b")
    with pytest.raises(PermissionError):
        preview(req, TENANT, now=NOW)
    assert calls == []


def test_same_event_claimed_by_two_incidents_is_complete_but_not_consistent():
    req = request()
    req.evidence.append(req.evidence[0].model_copy(update={"incident_id": "inc-2"}))
    result = preview(req, TENANT, now=NOW)
    assert result["evidence_duplicates"] == 0
    assert result["unmatched_evidence"] == 0
    assert result["groups"][0]["evidence_covered_events"] == 1
    assert result["groups"][0]["evidence_missing_events"] == 0
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is False
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False


@pytest.mark.parametrize("invalid_age", [True, 60.5, "60"])
def test_join_rejects_mutated_freshness_type_even_with_no_evidence(invalid_age):
    req = request()
    req.evidence = []
    req.max_age_seconds = invalid_age
    with pytest.raises(ValueError, match="freshness bound"):
        preview(req, TENANT, now=NOW)


def test_join_rejects_naive_clock_even_with_no_evidence():
    req = request()
    req.evidence = []
    with pytest.raises(ValueError, match="now requires timezone"):
        preview(req, TENANT, now=NOW.replace(tzinfo=None))


def test_join_rejects_invalid_clock_type_even_with_no_evidence():
    req = request()
    req.evidence = []
    with pytest.raises(ValueError, match="now requires timezone"):
        preview(req, TENANT, now="2026-11-10T12:00:00Z")


@pytest.mark.parametrize("invalid_tenant", ["", " ", " tenant-a ", None])
def test_join_rejects_invalid_authorized_tenant_identity(invalid_tenant):
    with pytest.raises(ValueError, match="request or tenant"):
        preview(request(), invalid_tenant, now=NOW)


def test_preview_revalidates_mutated_nested_correlation_signal():
    req = request()
    req.correlation.signals[0].severity = "unknown"
    with pytest.raises(ValidationError):
        preview(req, TENANT, now=NOW)


def test_preview_revalidates_mutated_nested_evidence_payload_limit():
    req = request()
    req.evidence[0].payload = {"blob": "x" * 100_000}
    with pytest.raises(ValidationError):
        preview(req, TENANT, now=NOW)


def test_preview_rejects_mutated_evidence_collection_over_limit():
    req = request()
    req.evidence = [req.evidence[0].model_copy(deep=True) for _ in range(501)]
    with pytest.raises(ValidationError):
        preview(req, TENANT, now=NOW)


def test_preview_never_marks_complete_or_consistent_when_signal_conflict_exists():
    req = request()
    original = req.correlation.signals[0]
    req.correlation.signals.append(original.model_copy(update={
        "service_name": "other-service", "severity": "critical",
    }))
    result = preview(req, TENANT, now=NOW)
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is False
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False
