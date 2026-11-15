"""Advisory, side-effect-free KPI aggregation for trusted LLM telemetry.

Normalizes ArgusLM-style request observations and Sentinel-style anomaly
counters without inventing measurements or crossing tenant boundaries.
This is not a live ingestion connector or a monitoring authorization service.
"""
from __future__ import annotations

import math
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LLMObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latency_ms: float | None = Field(default=None, ge=0)
    ttft_ms: float | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    tps: float | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    status: Literal["ok", "error", "degraded"]

    @field_validator("latency_ms", "ttft_ms", "tps", "estimated_cost_usd")
    @classmethod
    def finite_values(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("Non-finite KPI value")
        return value

    @model_validator(mode="after")
    def validate_timing(self):
        if (self.latency_ms is not None and self.ttft_ms is not None
                and self.ttft_ms > self.latency_ms):
            raise ValueError("TTFT exceeds request latency")
        return self


class LLMKPIRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    model_id: str = Field(min_length=1, max_length=128, pattern=r"\A[a-zA-Z0-9][a-zA-Z0-9_./:-]*\Z")
    observations: list[LLMObservation] = Field(min_length=1, max_length=1000)
    sentinel_anomalies_total: int | None = Field(default=None, ge=0)
    sentinel_events_processed_total: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_sentinel(self):
        if (self.sentinel_anomalies_total is not None
                and self.sentinel_events_processed_total is not None
                and self.sentinel_anomalies_total > self.sentinel_events_processed_total):
            raise ValueError("Anomalies cannot exceed processed events")
        return self


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    low = math.floor(rank)
    high = math.ceil(rank)
    # Convex interpolation avoids overflow in (high - low) for finite values
    # and never returns a non-JSON infinity for an extreme sample.
    fraction = rank - low
    result = ordered[low] * (1.0 - fraction) + ordered[high] * fraction
    if not math.isfinite(result):
        raise ValueError("Non-finite LLM KPI percentile")
    return round(result, 3)


def _finite_sum(values: list[float]) -> float:
    """Never emit infinity when individually finite observations overflow."""
    try:
        total = math.fsum(values)
    except OverflowError as exc:
        raise ValueError("LLM KPI aggregate overflow") from exc
    if not math.isfinite(total):
        raise ValueError("Non-finite LLM KPI aggregate")
    return total


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    # Scale first so large finite observations with a finite mean do not
    # overflow in the intermediate sum.
    try:
        mean = math.fsum(value / len(values) for value in values)
    except OverflowError as exc:
        raise ValueError("LLM KPI mean overflow") from exc
    if not math.isfinite(mean):
        raise ValueError("Non-finite LLM KPI mean")
    return round(mean, 3)


def calculate_llm_kpis(request: LLMKPIRequest, authorized_tenant: UUID) -> dict:
    # Revalidate mutable Pydantic models at the computation boundary. This
    # also prevents callers from injecting forged tenant or KPI fields after
    # initial parsing.
    if not isinstance(request, LLMKPIRequest):
        raise ValueError("Invalid KPI request")
    request = LLMKPIRequest.model_validate(request.model_dump())
    if request.tenant_id != authorized_tenant:
        raise ValueError("Cross-tenant KPI aggregation rejected")

    rows = request.observations
    latencies = [x.latency_ms for x in rows if x.latency_ms is not None]
    ttfts = [x.ttft_ms for x in rows if x.ttft_ms is not None]
    throughputs = [x.tps for x in rows if x.tps is not None]
    costs = [x.estimated_cost_usd for x in rows if x.estimated_cost_usd is not None]
    input_token_values = [x.input_tokens for x in rows if x.input_tokens is not None]
    output_token_values = [x.output_tokens for x in rows if x.output_tokens is not None]
    failures = sum(x.status == "error" for x in rows)
    successful = sum(x.status == "ok" for x in rows)
    degraded = sum(x.status == "degraded" for x in rows)
    total = len(rows)
    anomalies = request.sentinel_anomalies_total
    processed = request.sentinel_events_processed_total

    return {
        "tenant_id": str(authorized_tenant),
        "model_id": request.model_id,
        "sample_count": total,
        "success_rate_pct": round(100 * successful / total, 3),
        "error_rate_pct": round(100 * failures / total, 3),
        "degraded_rate_pct": round(100 * degraded / total, 3),
        "latency_coverage": round(len(latencies) / total, 3),
        "ttft_coverage": round(len(ttfts) / total, 3),
        "throughput_coverage": round(len(throughputs) / total, 3),
        "latency_p50_ms": _percentile(latencies, 0.5),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "latency_p99_ms": _percentile(latencies, 0.99),
        "ttft_p95_ms": _percentile(ttfts, 0.95),
        "mean_tps": _mean(throughputs),
        # A partial sum must not masquerade as total model usage.
        "total_input_tokens": sum(input_token_values) if len(input_token_values) == total else None,
        "total_output_tokens": sum(output_token_values) if len(output_token_values) == total else None,
        "input_token_coverage": round(len(input_token_values) / total, 3),
        "output_token_coverage": round(len(output_token_values) / total, 3),
        "estimated_cost_usd": round(_finite_sum(costs), 6) if len(costs) == total else None,
        "cost_coverage": round(len(costs) / total, 3),
        "measurement_coverage": {
            "latency_ms": {"measured": len(latencies), "missing": total - len(latencies), "total": total},
            "ttft_ms": {"measured": len(ttfts), "missing": total - len(ttfts), "total": total},
            "tps": {"measured": len(throughputs), "missing": total - len(throughputs), "total": total},
            "estimated_cost_usd": {"measured": len(costs), "missing": total - len(costs), "total": total},
            "input_tokens": {"measured": len(input_token_values), "missing": total - len(input_token_values), "total": total},
            "output_tokens": {"measured": len(output_token_values), "missing": total - len(output_token_values), "total": total},
        },
        "sample_window_state": "UNVERIFIED",
        "sample_provenance_state": "UNVERIFIED",
        "sentinel_anomaly_rate_pct": (
            round(100 * anomalies / processed, 3)
            if anomalies is not None and processed is not None and processed > 0 else None
        ),
        "sentinel_anomalies_total": anomalies,
        "sentinel_events_processed_total": processed,
        "data_source": "caller_supplied_preview",
        "authoritative": False,
        "production_qualified": False,
    }
