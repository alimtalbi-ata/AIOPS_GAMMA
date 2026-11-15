"""UC07: advisory LLM SLO preview, no production qualification."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.reused.llm_kpi import LLMKPIRequest
from app.reused.llm_slo import LLMSLOPreviewRequest, evaluate_llm_slo_preview


def make_request(tenant, observations, **options):
    thresholds = dict(
        min_samples=2, min_latency_coverage=1,
        min_success_rate_pct=90, max_latency_p95_ms=200,
    )
    thresholds.update(options)
    return LLMSLOPreviewRequest(
        kpis=LLMKPIRequest(
            tenant_id=tenant, model_id="model/test", observations=observations
        ),
        **thresholds,
    )


def test_slo_preview_pass_is_not_authoritative():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok", "latency_ms": 150},
    ])
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "PASS_PREVIEW"
    assert result["authoritative"] is False
    assert result["production_qualified"] is False
    assert result["live_remediation_authorized"] is False


def test_slo_preview_breach():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "error", "latency_ms": 250},
    ])
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "BREACH_PREVIEW"
    assert result["checks"]["success_rate_pct"]["passed"] is False
    assert result["checks"]["latency_p95_ms"]["passed"] is False


def test_missing_latency_does_not_pass_slo():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok"},
    ])
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "INSUFFICIENT_DATA"
    assert result["checks"]["latency_coverage"]["passed"] is False


def test_slo_rejects_cross_tenant_and_mutated_samples():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok", "latency_ms": 100},
    ])
    with pytest.raises(ValueError, match="Cross-tenant"):
        evaluate_llm_slo_preview(req, uuid4())
    req.kpis.observations[0].latency_ms = -1
    with pytest.raises(ValidationError):
        evaluate_llm_slo_preview(req, tenant)


def test_invalid_slo_threshold_is_rejected():
    tenant = uuid4()
    with pytest.raises(ValidationError):
        make_request(tenant, [{"status": "ok"}], min_samples=0)
