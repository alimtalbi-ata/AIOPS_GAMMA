"""Read-only LLM SLO evaluation on caller-supplied samples (UC07).

This preview cannot establish production SLO compliance: telemetry is not
authenticated, time-windowed, or independently verified.
"""
from __future__ import annotations

import math
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.reused.llm_kpi import LLMKPIRequest, calculate_llm_kpis


class LLMSLOPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kpis: LLMKPIRequest
    min_samples: int = Field(default=30, ge=1, le=1000)
    min_latency_coverage: float = Field(default=0.95, gt=0, le=1, allow_inf_nan=False)
    min_success_rate_pct: float = Field(default=99.0, ge=0, le=100, allow_inf_nan=False)
    max_latency_p95_ms: float = Field(default=2000.0, gt=0, le=3600000, allow_inf_nan=False)
    max_ttft_p95_ms: float | None = Field(default=None, gt=0, le=3600000, allow_inf_nan=False)
    min_throughput_tps: float | None = Field(default=None, gt=0, le=1000000, allow_inf_nan=False)
    max_mean_cost_usd: float | None = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)


def evaluate_llm_slo_preview(request: LLMSLOPreviewRequest, tenant: UUID) -> dict:
    if not isinstance(request, LLMSLOPreviewRequest):
        raise ValueError("Invalid SLO preview request")
    request = LLMSLOPreviewRequest.model_validate(request.model_dump())
    kpis = calculate_llm_kpis(request.kpis, tenant)
    observations = request.kpis.observations
    count = len(observations)
    measured = [row.latency_ms for row in observations if row.latency_ms is not None]
    success = sum(row.status == "ok" for row in observations)
    # Compare unrounded values: rounding must never turn a breach into a pass.
    sample_ok = count >= request.min_samples
    coverage_ok = len(measured) / count >= request.min_latency_coverage
    success_ok = 100 * success / count >= request.min_success_rate_pct
    ordered = sorted(measured)
    if ordered:
        rank = (len(ordered) - 1) * 0.95
        lower, upper = math.floor(rank), math.ceil(rank)
        raw_p95 = ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)
    else:
        raw_p95 = None
    latency_ok = raw_p95 is not None and raw_p95 <= request.max_latency_p95_ms
    ttfts = sorted(row.ttft_ms for row in observations if row.ttft_ms is not None)
    if ttfts:
        ttft_rank = (len(ttfts) - 1) * 0.95
        ttft_lower, ttft_upper = math.floor(ttft_rank), math.ceil(ttft_rank)
        raw_ttft_p95 = ttfts[ttft_lower] + (
            ttfts[ttft_upper] - ttfts[ttft_lower]
        ) * (ttft_rank - ttft_lower)
    else:
        raw_ttft_p95 = None
    ttft_enabled = request.max_ttft_p95_ms is not None
    ttft_complete = len(ttfts) == count
    ttft_ok = (
        raw_ttft_p95 is not None
        and ttft_enabled
        and raw_ttft_p95 <= request.max_ttft_p95_ms
    ) if ttft_enabled else None
    throughput_enabled = request.min_throughput_tps is not None
    throughputs = [row.tps for row in observations if row.tps is not None]
    throughput_complete = len(throughputs) == count
    # Summing individually finite measurements can still overflow to infinity.
    # A preview must fail closed rather than emit non-JSON numeric values.
    if throughputs:
        try:
            raw_mean_tps = math.fsum(throughputs) / len(throughputs)
        except OverflowError as exc:
            raise ValueError("Throughput aggregation overflow") from exc
        if not math.isfinite(raw_mean_tps):
            raise ValueError("Non-finite throughput aggregate")
    else:
        raw_mean_tps = None
    throughput_ok = (
        raw_mean_tps is not None
        and raw_mean_tps >= request.min_throughput_tps
    ) if throughput_enabled else None
    cost_enabled = request.max_mean_cost_usd is not None
    costs = [row.estimated_cost_usd for row in observations if row.estimated_cost_usd is not None]
    cost_complete = len(costs) == count
    if costs:
        try:
            raw_mean_cost = math.fsum(costs) / len(costs)
        except OverflowError as exc:
            raise ValueError("Cost aggregation overflow") from exc
        if not math.isfinite(raw_mean_cost):
            raise ValueError("Non-finite cost aggregate")
    else:
        raw_mean_cost = None
    cost_ok = (
        raw_mean_cost is not None
        and raw_mean_cost <= request.max_mean_cost_usd
    ) if cost_enabled else None
    # Report measured breaches even when the overall assessment is
    # insufficient; never mistake missing latency measurements for a pass.
    observed_breaches = []
    if not success_ok:
        observed_breaches.append("success_rate_pct")
    if raw_p95 is not None and not latency_ok:
        observed_breaches.append("latency_p95_ms")
    if ttft_enabled and raw_ttft_p95 is not None and not ttft_ok:
        observed_breaches.append("ttft_p95_ms")
    if throughput_enabled and raw_mean_tps is not None and not throughput_ok:
        observed_breaches.append("mean_tps")
    if cost_enabled and raw_mean_cost is not None and not cost_ok:
        observed_breaches.append("mean_cost_usd")
    # A passing SLO requires adequate sample and metric coverage.
    # The selected sample may be biased when latency is missing. Even if the
    # configured coverage minimum is met, a partial p95 cannot certify a pass.
    latency_complete = len(measured) == count
    insufficient_reasons = []
    if not sample_ok:
        insufficient_reasons.append("sample_count_below_minimum")
    if not coverage_ok:
        insufficient_reasons.append("latency_coverage_below_minimum")
    if not latency_complete:
        insufficient_reasons.append("latency_measurements_incomplete")
    if ttft_enabled and not ttft_complete:
        insufficient_reasons.append("ttft_measurements_incomplete")
    if throughput_enabled and not throughput_complete:
        insufficient_reasons.append("throughput_measurements_incomplete")
    if cost_enabled and not cost_complete:
        insufficient_reasons.append("cost_measurements_incomplete")
    if insufficient_reasons:
        state = "INSUFFICIENT_DATA"
    elif (success_ok and latency_ok
          and (not ttft_enabled or ttft_ok)
          and (not throughput_enabled or throughput_ok)
          and (not cost_enabled or cost_ok)):
        state = "PASS_PREVIEW"
    else:
        state = "BREACH_PREVIEW"
    return {
        "tenant_id": str(tenant),
        "model_id": request.kpis.model_id,
        "state": state,
        "observed_breaches": observed_breaches,
        "insufficient_data_reasons": insufficient_reasons,
        "latency_complete": latency_complete,
        "ttft_complete": ttft_complete if ttft_enabled else None,
        "throughput_complete": throughput_complete if throughput_enabled else None,
        "cost_complete": cost_complete if cost_enabled else None,
        "checks": {
            "sample_count": {"value": count, "minimum": request.min_samples, "passed": sample_ok},
            "latency_coverage": {
                "value": len(measured) / count,
                "minimum": request.min_latency_coverage,
                "passed": coverage_ok,
            },
            "success_rate_pct": {
                "value": 100 * success / count,
                "minimum": request.min_success_rate_pct,
                "passed": success_ok,
            },
            "latency_p95_ms": {
                "value": raw_p95,
                "maximum": request.max_latency_p95_ms,
                "passed": latency_ok if raw_p95 is not None else None,
            },
            "ttft_p95_ms": {
                "value": raw_ttft_p95 if ttft_enabled else None,
                "maximum": request.max_ttft_p95_ms,
                "passed": ttft_ok,
                "enabled": ttft_enabled,
            },
            "mean_tps": {
                "value": raw_mean_tps if throughput_enabled else None,
                "minimum": request.min_throughput_tps,
                "passed": throughput_ok,
                "enabled": throughput_enabled,
            },
            "mean_cost_usd": {
                "value": raw_mean_cost if cost_enabled else None,
                "maximum": request.max_mean_cost_usd,
                "passed": cost_ok,
                "enabled": cost_enabled,
            },
        },
        "data_source": "caller_supplied_preview",
        "authoritative": False,
        "production_qualified": False,
        "live_remediation_authorized": False,
    }
