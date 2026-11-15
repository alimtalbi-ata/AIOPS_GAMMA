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
    assert result["observed_breaches"] == ["success_rate_pct", "latency_p95_ms"]


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


def test_insufficient_data_still_reports_observed_success_breach():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "error", "latency_ms": 100},
        {"status": "error"},
    ])
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "INSUFFICIENT_DATA"
    assert result["observed_breaches"] == ["success_rate_pct"]
    assert result["checks"]["latency_coverage"]["passed"] is False


def test_missing_all_latency_is_unknown_not_latency_breach():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok"},
        {"status": "ok"},
    ])
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "INSUFFICIENT_DATA"
    assert result["checks"]["latency_p95_ms"]["passed"] is None
    assert result["observed_breaches"] == []


def test_zero_latency_coverage_requirement_is_rejected():
    tenant = uuid4()
    with pytest.raises(ValidationError):
        make_request(tenant, [{"status": "ok"}], min_latency_coverage=0)


def test_p95_threshold_uses_unrounded_measurement():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100.0001},
        {"status": "ok", "latency_ms": 100.0004},
    ], max_latency_p95_ms=100.0003)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "BREACH_PREVIEW"
    assert result["observed_breaches"] == ["latency_p95_ms"]
    assert result["checks"]["latency_p95_ms"]["value"] > 100.0003


def test_slo_route_requires_auth_and_prevents_caching(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.settings import settings

    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok", "latency_ms": 150},
    ])
    path = "/api/v1/observability/llm/slo/preview"
    with TestClient(app) as client:
        denied = client.post(path, json=req.model_dump(mode="json"))
        allowed = client.post(
            path, json=req.model_dump(mode="json"),
            headers={"X-Internal-Api-Key": "test-secret",
                     "X-Tenant-Id": str(tenant)},
        )
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.headers["cache-control"] == "no-store"
    assert allowed.json()["state"] == "PASS_PREVIEW"


@pytest.mark.parametrize("field,value", [
    ("min_latency_coverage", float("nan")),
    ("min_latency_coverage", float("inf")),
    ("min_success_rate_pct", float("nan")),
    ("min_success_rate_pct", float("-inf")),
    ("max_latency_p95_ms", float("nan")),
    ("max_latency_p95_ms", float("inf")),
])
def test_nonfinite_slo_thresholds_rejected(field, value):
    with pytest.raises(ValidationError):
        make_request(uuid4(), [{"status": "ok"}], **{field: value})


def test_mutated_slo_threshold_is_revalidated_before_computation():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok", "latency_ms": 120},
    ])
    req.max_latency_p95_ms = float("nan")
    with pytest.raises(ValidationError):
        evaluate_llm_slo_preview(req, tenant)
