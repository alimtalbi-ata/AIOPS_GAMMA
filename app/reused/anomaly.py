"""Robust, bounded time-series anomaly *preview* — not an incident authority.

Independent implementation based on IncidentFox's metric-analysis tool
categories. Median/MAD is resilient to isolated spikes but does not model
seasonality, forecast capacity or assert causality.
"""
from __future__ import annotations

from math import isfinite
from statistics import median

from pydantic import BaseModel, Field, model_validator


class MetricSeries(BaseModel):
    metric_name: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.:-]+$")
    values: list[float] = Field(min_length=10, max_length=1000)
    threshold: float = Field(default=3.5, ge=2, le=10)

    @model_validator(mode="after")
    def finite(self):
        if not all(isfinite(v) and abs(v) <= 1e15 for v in self.values):
            raise ValueError("Series contains non-finite or excessive measurements")
        return self


def detect_anomalies(series: MetricSeries) -> dict:
    baseline = median(series.values)
    mad = median(abs(v - baseline) for v in series.values)
    # A zero MAD cannot establish a statistically calibrated confidence.
    # Report an 'unknown' threshold state rather than treating any change as anomaly.
    if mad == 0:
        return {
            "metric_name": series.metric_name, "state": "INSUFFICIENT_VARIABILITY",
            "median": baseline, "mad": mad, "anomalies": [], "truncated": False,
            "causal_inference": False, "live_remediation_authorized": False,
        }
    points = [
        {"index": i, "value": v, "robust_z": round(0.6745 * (v - baseline) / mad, 4)}
        for i, v in enumerate(series.values)
        if abs(0.6745 * (v - baseline) / mad) >= series.threshold
    ]
    return {
        "metric_name": series.metric_name, "state": "EVALUATED",
        "median": baseline, "mad": mad, "anomalies": points[:100],
        "truncated": len(points) > 100,
        "causal_inference": False, "live_remediation_authorized": False,
    }
