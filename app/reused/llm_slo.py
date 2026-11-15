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
    min_latency_coverage: float = Field(default=0.95, gt=0, le=1)
    min_success_rate_pct: float = Field(default=99.0, ge=0, le=100)
    max_latency_p95_ms: float = Field(default=2000.0, gt=0, le=3600000)


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
    # Report measured breaches even when the overall assessment is
    # insufficient; never mistake missing latency measurements for a pass.
    observed_breaches = []
    if not success_ok:
        observed_breaches.append("success_rate_pct")
    if raw_p95 is not None and not latency_ok:
        observed_breaches.append("latency_p95_ms")
    # A passing SLO requires adequate sample and metric coverage.
    if not sample_ok or not coverage_ok:
        state = "INSUFFICIENT_DATA"
    elif success_ok and latency_ok:
        state = "PASS_PREVIEW"
    else:
        state = "BREACH_PREVIEW"
    return {
        "tenant_id": str(tenant),
        "model_id": request.kpis.model_id,
        "state": state,
        "observed_breaches": observed_breaches,
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
        },
        "data_source": "caller_supplied_preview",
        "authoritative": False,
        "production_qualified": False,
        "live_remediation_authorized": False,
    }
