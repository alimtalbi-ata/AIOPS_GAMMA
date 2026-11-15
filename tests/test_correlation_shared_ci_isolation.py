"""UC02/P3: unverified shared CI must not correlate distinct services."""
from datetime import datetime, timezone

from app.reused.correlation import CorrelationSignal, correlate


def signal(service, event_id, ci_id):
    return CorrelationSignal(
        source="otel", external_event_id=event_id,
        service_name=service, environment="production",
        ci_id=ci_id, symptom_key="high-latency",
        severity="major", status="firing",
        observed_at=datetime(2026, 11, 15, 12, tzinfo=timezone.utc),
    )


def test_shared_ci_across_services_never_merges_preview():
    result = correlate([
        signal("checkout", "e1", "shared-ci"),
        signal("billing", "e2", "shared-ci"),
    ], "11111111-1111-4111-8111-111111111111")
    assert len(result["groups"]) == 2
    assert {g["service_name"] for g in result["groups"]} == {"checkout", "billing"}
    assert all(g["event_count"] == 1 for g in result["groups"])
    assert all(g["impact_state"] == "UNKNOWN_UNTIL_CMDB_VERIFIED" for g in result["groups"])


def test_same_service_and_ci_still_correlates():
    result = correlate([
        signal("checkout", "e1", "shared-ci"),
        signal("checkout", "e2", "shared-ci"),
    ], "11111111-1111-4111-8111-111111111111")
    assert len(result["groups"]) == 1
    assert result["groups"][0]["event_count"] == 2
