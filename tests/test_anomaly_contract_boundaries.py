"""Isolated safety and numerical boundaries for anomaly previews."""
import pytest
from pydantic import ValidationError

from app.reused.anomaly import MetricSeries, detect_anomalies


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf"), 1e16, -1e16])
def test_nonfinite_and_excessive_samples_rejected(invalid):
    with pytest.raises(ValidationError):
        MetricSeries(metric_name="latency_ms", values=[10.0] * 9 + [invalid])


@pytest.mark.parametrize("size", [9, 1001])
def test_series_size_is_bounded(size):
    with pytest.raises(ValidationError):
        MetricSeries(metric_name="cpu", values=[1.0] * size)


@pytest.mark.parametrize("threshold", [1.99, 10.01])
def test_threshold_is_bounded(threshold):
    with pytest.raises(ValidationError):
        MetricSeries(metric_name="cpu", values=[1.0] * 10, threshold=threshold)


def test_zero_mad_never_claims_anomaly_or_live_authority():
    result = detect_anomalies(MetricSeries(metric_name="cpu", values=[1.0] * 10 + [999.0]))
    assert result["state"] == "INSUFFICIENT_VARIABILITY"
    assert result["anomalies"] == []
    assert result["truncated"] is False
    assert result["causal_inference"] is False
    assert result["live_remediation_authorized"] is False


def test_anomaly_output_is_bounded_and_never_authorizes_remediation():
    values = [float(i % 3) for i in range(600)] + [1000.0] * 400
    result = detect_anomalies(MetricSeries(metric_name="cpu", values=values))
    assert result["state"] == "EVALUATED"
    assert len(result["anomalies"]) <= 100
    assert result["truncated"] is True
    assert result["causal_inference"] is False
    assert result["live_remediation_authorized"] is False
