from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.reused.alertmanager import AlertNormalizeRequest, normalize_alerts
from app.reused.anomaly import MetricSeries, detect_anomalies


def alert(fingerprint="abc", status="firing"):
    return {
        "status": status, "fingerprint": fingerprint,
        "labels": {"alertname": "HighLatency", "service": "checkout", "severity": "critical"},
        "annotations": {"summary": "Example only", "runbook_url": "https://external.invalid/execute"},
        "startsAt": "2026-11-09T12:00:00Z",
    }


def request(alerts, source="alertmanager"):
    return AlertNormalizeRequest(source=source, environment="prod", payload={"alerts": alerts})


def test_alertmanager_preserves_source_and_no_untrusted_tool_refs():
    items = normalize_alerts(request([alert()]))
    assert len(items) == 1
    assert items[0].service_name == "checkout"
    assert items[0].severity == "critical"
    assert items[0].ci_id is None
    assert items[0].evidence_refs == []
    assert "external.invalid" not in items[0].model_dump_json()


def test_resolved_and_firing_are_distinct_transitions():
    a = normalize_alerts(request([alert(status="firing")]))[0]
    b = normalize_alerts(request([alert(status="resolved")]))[0]
    assert a.external_event_id != b.external_event_id
    assert b.status == "resolved"


def test_duplicate_id_is_stable_for_replays():
    a = normalize_alerts(request([alert()]))[0]
    b = normalize_alerts(request([alert()]))[0]
    assert a.external_event_id == b.external_event_id


def test_reject_naive_time():
    item = alert()
    item["startsAt"] = "2026-11-09T12:00:00"
    with pytest.raises(ValidationError):
        request([item])


def test_reject_missing_service():
    item = alert()
    del item["labels"]["service"]
    with pytest.raises(ValueError):
        normalize_alerts(request([item]))


def test_reject_oversized_batches():
    with pytest.raises(ValidationError):
        request([alert(str(i)) for i in range(101)])


def test_detect_robust_outlier():
    values = [9, 10, 11, 9, 10, 11, 9, 10, 11, 10, 100]
    result = detect_anomalies(MetricSeries(metric_name="latency_ms", values=values))
    assert result["state"] == "EVALUATED"
    assert any(p["index"] == 10 for p in result["anomalies"])
    assert not result["causal_inference"]


def test_constant_baseline_is_unknown_not_false_certainty():
    result = detect_anomalies(MetricSeries(metric_name="latency_ms", values=[5.0] * 11))
    assert result["state"] == "INSUFFICIENT_VARIABILITY"


@pytest.mark.parametrize("values", [[1.0]*9, [0.0]*9+[float("nan")], [0.0]*9+[float("inf")]])
def test_reject_bad_series(values):
    with pytest.raises(ValidationError):
        MetricSeries(metric_name="cpu", values=values)
