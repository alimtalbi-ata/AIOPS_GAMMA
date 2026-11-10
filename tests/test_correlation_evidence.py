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
