"""Read-only LLM SLO evaluation on caller-supplied samples (UC07).

This preview cannot establish production SLO compliance: telemetry is not
authenticated or independently verified; optional caller-declared windows are not attested.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.reused.llm_kpi import LLMKPIRequest


class LLMSLOPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kpis: LLMKPIRequest
    window_start: datetime | None = None
    window_end: datetime | None = None

    @field_validator("window_start", "window_end", mode="before")
    @classmethod
    def reject_ambiguous_window_timestamp(cls, value):
        if value is not None and not isinstance(value, (datetime, str)):
            raise ValueError("SLO window timestamp must be ISO-8601 or datetime")
        if isinstance(value, str) and (not value or value.strip() != value
                                       or value.lstrip("+-").replace(".", "", 1).isdigit()):
            raise ValueError("SLO window timestamp must be ISO-8601")
        return value

    @model_validator(mode="after")
    def validate_declared_window(self):
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("Both SLO window bounds are required")
        if self.window_start is None:
            return self
        start, end = self.window_start, self.window_end
        if (start.tzinfo is None or start.utcoffset() is None
                or end.tzinfo is None or end.utcoffset() is None):
            raise ValueError("SLO window bounds must be timezone-aware")
        if not start < end or end - start > timedelta(hours=24):
            raise ValueError("SLO window must be positive and at most 24 hours")
        if end > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("SLO window cannot end in the future")
        for observation in self.kpis.observations:
            if observation.observed_at is None:
                raise ValueError("All SLO observations require timestamps for a declared window")
            if not start <= observation.observed_at < end:
                raise ValueError("SLO observation falls outside the declared window")
        return self

    min_window_span_coverage: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    max_window_gap_ratio: float = Field(default=1.0, gt=0, le=1, allow_inf_nan=False)
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
    # SLO decisions use their own unrounded metrics. Do not compute unrelated
    # KPI totals: a finite mean cost can be valid even when the aggregate
    # lifetime cost would overflow floating point.
    if request.kpis.tenant_id != tenant:
        raise ValueError("Cross-tenant KPI aggregation rejected")
    observations = request.kpis.observations
    count = len(observations)
    window_span_coverage = None
    distinct_sample_timestamps = None
    max_observed_gap_ratio = None
    if request.window_start is not None:
        observed_times = [row.observed_at for row in observations]
        distinct_sample_timestamps = len(set(observed_times))
        # Include both window edges: endpoint-only samples cannot prove
        # continuous coverage across a long silent interval.
        points = [request.window_start, *sorted(set(observed_times)), request.window_end]
        largest_gap = max(right - left for left, right in zip(points, points[1:]))
        max_observed_gap_ratio = largest_gap / (request.window_end - request.window_start)
        observed_span = max(observed_times) - min(observed_times)
        window_span_coverage = observed_span / (request.window_end - request.window_start)
        # Temporal spread is only a weak proxy for completeness; the source
        # remains caller-supplied and unverified even when this check passes.

    measured = [row.latency_ms for row in observations if row.latency_ms is not None]
    success = sum(row.status == "ok" for row in observations)
    # Compare unrounded values: rounding must never turn a breach into a pass.
    sample_ok = count >= request.min_samples
    coverage_ok = len(measured) / count >= request.min_latency_coverage
    success_ok = 100 * success / count >= request.min_success_rate_pct
    # A missing latency measurement must not conceal an observed breach, but
    # incomplete optional metrics cannot produce a definitive PASS or BREACH.
    # Keep metric-level check results tri-state until coverage is complete.
    ordered = sorted(measured)
    if ordered:
        rank = (len(ordered) - 1) * 0.95
        lower, upper = math.floor(rank), math.ceil(rank)
        fraction = rank - lower
        raw_p95 = ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction
        if not math.isfinite(raw_p95):
            raise ValueError("Non-finite latency p95")
    else:
        raw_p95 = None
    latency_complete = len(measured) == count
    latency_ok = (
        raw_p95 <= request.max_latency_p95_ms
        if latency_complete and raw_p95 is not None else None
    )
    ttfts = sorted(row.ttft_ms for row in observations if row.ttft_ms is not None)
    if ttfts:
        ttft_rank = (len(ttfts) - 1) * 0.95
        ttft_lower, ttft_upper = math.floor(ttft_rank), math.ceil(ttft_rank)
        fraction = ttft_rank - ttft_lower
        raw_ttft_p95 = (
            ttfts[ttft_lower] * (1.0 - fraction)
            + ttfts[ttft_upper] * fraction
        )
        if not math.isfinite(raw_ttft_p95):
            raise ValueError("Non-finite TTFT p95")
    else:
        raw_ttft_p95 = None
    ttft_enabled = request.max_ttft_p95_ms is not None
    ttft_complete = len(ttfts) == count
    ttft_ok = (
        raw_ttft_p95 <= request.max_ttft_p95_ms
        if ttft_complete and raw_ttft_p95 is not None else None
    ) if ttft_enabled else None
    throughput_enabled = request.min_throughput_tps is not None
    throughputs = [row.tps for row in observations if row.tps is not None]
    throughput_complete = len(throughputs) == count
    # Scale before summing: finite observations can have a finite mean even
    # when their unscaled sum would overflow. Still reject non-finite results.
    if throughputs:
        try:
            raw_mean_tps = math.fsum(value / len(throughputs) for value in throughputs)
        except OverflowError as exc:
            raise ValueError("Throughput aggregation overflow") from exc
        if not math.isfinite(raw_mean_tps):
            raise ValueError("Non-finite throughput aggregate")
    else:
        raw_mean_tps = None
    throughput_ok = (
        raw_mean_tps >= request.min_throughput_tps
        if throughput_complete and raw_mean_tps is not None else None
    ) if throughput_enabled else None
    cost_enabled = request.max_mean_cost_usd is not None
    costs = [row.estimated_cost_usd for row in observations if row.estimated_cost_usd is not None]
    cost_complete = len(costs) == count
    if costs:
        try:
            raw_mean_cost = math.fsum(value / len(costs) for value in costs)
        except OverflowError as exc:
            raise ValueError("Cost aggregation overflow") from exc
        if not math.isfinite(raw_mean_cost):
            raise ValueError("Non-finite cost aggregate")
    else:
        raw_mean_cost = None
    cost_ok = (
        raw_mean_cost <= request.max_mean_cost_usd
        if cost_complete and raw_mean_cost is not None else None
    ) if cost_enabled else None
    # Report measured breaches even when the overall assessment is
    # insufficient; never mistake missing latency measurements for a pass.
    observed_breaches = []
    if not success_ok:
        observed_breaches.append("success_rate_pct")
    if latency_ok is False:
        observed_breaches.append("latency_p95_ms")
    if ttft_ok is False:
        observed_breaches.append("ttft_p95_ms")
    if throughput_ok is False:
        observed_breaches.append("mean_tps")
    if cost_ok is False:
        observed_breaches.append("mean_cost_usd")
    # A passing SLO requires adequate sample and metric coverage.
    # The selected sample may be biased when latency is missing. Even if the
    # configured coverage minimum is met, a partial p95 cannot certify a pass.
    insufficient_reasons = []
    if not sample_ok:
        insufficient_reasons.append("sample_count_below_minimum")
    if (max_observed_gap_ratio is not None
            and max_observed_gap_ratio > request.max_window_gap_ratio):
        insufficient_reasons.append("window_sample_gap_above_maximum")
    if distinct_sample_timestamps is not None and distinct_sample_timestamps < 2:
        insufficient_reasons.append("window_distinct_timestamps_below_minimum")
    if (window_span_coverage is not None
            and window_span_coverage < request.min_window_span_coverage):
        insufficient_reasons.append("window_sample_span_below_minimum")
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
        # Explicit denominators prevent UI consumers from mistaking a partial
        # metric for a measurement of every model request.
        "measurement_coverage": {
            "latency_ms": {"measured": len(measured), "missing": count - len(measured), "total": count},
            "ttft_ms": {"measured": len(ttfts), "missing": count - len(ttfts), "total": count},
            "tps": {"measured": len(throughputs), "missing": count - len(throughputs), "total": count},
            "estimated_cost_usd": {"measured": len(costs), "missing": count - len(costs), "total": count},
        },
        "sample_window_state": ("CALLER_DECLARED_UNVERIFIED" if request.window_start is not None else "UNVERIFIED"),
        "declared_window": (
            {"start": request.window_start.isoformat(), "end": request.window_end.isoformat(), "end_exclusive": True,
             "duration_seconds": (request.window_end - request.window_start).total_seconds(),
             "sample_count": count,
             "first_observed_at": min(row.observed_at for row in observations).isoformat(),
             "last_observed_at": max(row.observed_at for row in observations).isoformat()}
            if request.window_start is not None else None
        ),
        "sample_provenance_state": "UNVERIFIED",
        "distinct_sample_timestamps": distinct_sample_timestamps,
        "max_observed_gap_ratio": max_observed_gap_ratio,
        "max_window_gap_ratio": request.max_window_gap_ratio if max_observed_gap_ratio is not None else None,
        "window_span_coverage": window_span_coverage,
        "min_window_span_coverage": request.min_window_span_coverage if window_span_coverage is not None else None,
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
                "passed": latency_ok,
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
