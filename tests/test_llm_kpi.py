"""KPI preview tests grounded in Sentinel and ArgusLM measurement units."""
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.reused.llm_kpi import LLMKPIRequest, calculate_llm_kpis
from app.settings import settings


def request(tenant, **overrides):
    values = {
        "tenant_id": tenant,
        "model_id": "provider/model",
        "observations": [
            {"status": "ok", "latency_ms": 100, "ttft_ms": 20,
             "tps": 50, "input_tokens": 10, "output_tokens": 5,
             "estimated_cost_usd": 0.01},
            {"status": "error", "latency_ms": 300, "ttft_ms": 60,
             "tps": 0, "input_tokens": 20, "output_tokens": 0,
             "estimated_cost_usd": 0.02},
        ],
        "sentinel_anomalies_total": 2,
        "sentinel_events_processed_total": 20,
    }
    values.update(overrides)
    return LLMKPIRequest(**values)


def test_kpis_and_units():
    tenant = uuid4()
    result = calculate_llm_kpis(request(tenant), tenant)
    assert result["sample_count"] == 2
    assert result["success_rate_pct"] == 50
    assert result["error_rate_pct"] == 50
    assert result["latency_p50_ms"] == 200
    assert result["latency_p95_ms"] == 290
    assert result["ttft_p95_ms"] == 58
    assert result["mean_tps"] == 25
    assert result["total_input_tokens"] == 30
    assert result["total_output_tokens"] == 5
    assert result["estimated_cost_usd"] == 0.03
    assert result["sentinel_anomaly_rate_pct"] == 10
    assert result["authoritative"] is False


def test_incomplete_cost_is_unknown_not_zero():
    tenant = uuid4()
    result = calculate_llm_kpis(request(tenant, observations=[
        {"status": "ok", "estimated_cost_usd": 0},
        {"status": "degraded"},
    ]), tenant)
    assert result["estimated_cost_usd"] is None
    assert result["cost_coverage"] == 0.5
    assert result["latency_p95_ms"] is None
    assert result["total_output_tokens"] is None


def test_zero_processed_events_yields_unknown_anomaly_rate():
    tenant = uuid4()
    result = calculate_llm_kpis(request(tenant,
        sentinel_anomalies_total=0, sentinel_events_processed_total=0), tenant)
    assert result["sentinel_anomaly_rate_pct"] is None


def test_reject_cross_tenant():
    tenant = uuid4()
    with pytest.raises(ValueError, match="Cross-tenant"):
        calculate_llm_kpis(request(tenant), uuid4())


@pytest.mark.parametrize("invalid", [
    {"status": "ok", "latency_ms": -1},
    {"status": "ok", "latency_ms": 10, "ttft_ms": 20},
    {"status": "ok", "tps": float("inf")},
    {"status": "ok", "estimated_cost_usd": float("nan")},
    {"status": "unknown"},
    {"status": "ok", "raw_prompt": "secret"},
])
def test_reject_invalid_observations(invalid):
    with pytest.raises(ValidationError):
        request(uuid4(), observations=[invalid])


def test_reject_invalid_sentinel_counters():
    with pytest.raises(ValidationError):
        request(uuid4(), sentinel_anomalies_total=21,
                sentinel_events_processed_total=20)


def test_kpi_route_requires_internal_auth(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    tenant = uuid4()
    with TestClient(app) as client:
        response = client.post("/api/v1/observability/llm/kpis/preview",
                               json=request(tenant).model_dump(mode="json"))
    assert response.status_code == 401


def test_kpi_route_blocks_cross_tenant(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    tenant = uuid4()
    with TestClient(app) as client:
        response = client.post("/api/v1/observability/llm/kpis/preview",
                               json=request(tenant).model_dump(mode="json"),
                               headers={"X-Internal-Api-Key": "test-secret",
                                        "X-Tenant-Id": str(uuid4())})
    assert response.status_code == 422


def test_kpi_route_success(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    tenant = uuid4()
    with TestClient(app) as client:
        response = client.post("/api/v1/observability/llm/kpis/preview",
                               json=request(tenant).model_dump(mode="json"),
                               headers={"X-Internal-Api-Key": "test-secret",
                                        "X-Tenant-Id": str(tenant)})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["data_source"] == "caller_supplied_preview"


def test_degraded_rate_and_metric_coverage_are_explicit():
    tenant = uuid4()
    req = request(tenant, observations=[
        {"status": "ok", "latency_ms": 100, "ttft_ms": 25, "tps": 10},
        {"status": "degraded", "latency_ms": 300},
        {"status": "error"},
    ])
    result = calculate_llm_kpis(req, tenant)
    assert result["success_rate_pct"] == pytest.approx(33.333)
    assert result["degraded_rate_pct"] == pytest.approx(33.333)
    assert result["error_rate_pct"] == pytest.approx(33.333)
    assert result["latency_coverage"] == pytest.approx(0.667)
    assert result["ttft_coverage"] == pytest.approx(0.333)
    assert result["throughput_coverage"] == pytest.approx(0.333)
    assert result["authoritative"] is False
    assert result["production_qualified"] is False


def test_mutated_kpi_observation_rejected_at_calculation_boundary():
    tenant = uuid4()
    req = request(tenant)
    req.observations[0].latency_ms = -1
    with pytest.raises(ValidationError):
        calculate_llm_kpis(req, tenant)


def test_mutated_kpi_tenant_rejected_at_calculation_boundary():
    tenant = uuid4()
    req = request(tenant)
    req.tenant_id = uuid4()
    with pytest.raises(ValueError, match="Cross-tenant"):
        calculate_llm_kpis(req, tenant)


def test_partial_token_samples_do_not_masquerade_as_total_usage():
    tenant = uuid4()
    result = calculate_llm_kpis(request(tenant, observations=[
        {"status": "ok", "input_tokens": 120, "output_tokens": 40},
        {"status": "error", "input_tokens": 30},
        {"status": "degraded"},
    ]), tenant)
    assert result["total_input_tokens"] is None
    assert result["total_output_tokens"] is None
    assert result["input_token_coverage"] == pytest.approx(0.667)
    assert result["output_token_coverage"] == pytest.approx(0.333)
    assert result["authoritative"] is False


def test_complete_zero_token_usage_is_known_zero():
    tenant = uuid4()
    result = calculate_llm_kpis(request(tenant, observations=[
        {"status": "ok", "input_tokens": 0, "output_tokens": 0},
        {"status": "error", "input_tokens": 0, "output_tokens": 0},
    ]), tenant)
    assert result["total_input_tokens"] == 0
    assert result["total_output_tokens"] == 0
    assert result["input_token_coverage"] == 1
    assert result["output_token_coverage"] == 1


def test_kpi_mean_of_extreme_finite_throughput_remains_finite():
    tenant = uuid4()
    req = request(tenant, observations=[
        {"status": "ok", "latency_ms": 100, "tps": 1e308},
        {"status": "ok", "latency_ms": 120, "tps": 1e308},
    ])
    result = calculate_llm_kpis(req, tenant)
    assert result["mean_tps"] == 1e308


def test_kpi_total_cost_overflow_fails_closed():
    tenant = uuid4()
    req = request(tenant, observations=[
        {"status": "ok", "latency_ms": 100, "estimated_cost_usd": 1e308},
        {"status": "ok", "latency_ms": 120, "estimated_cost_usd": 1e308},
    ])
    with pytest.raises(ValueError, match="aggregate overflow"):
        calculate_llm_kpis(req, tenant)


def test_kpi_mean_cost_does_not_masquerade_as_partial_total():
    tenant = uuid4()
    req = request(tenant, observations=[
        {"status": "ok", "latency_ms": 100, "estimated_cost_usd": 0.01},
        {"status": "ok", "latency_ms": 120},
    ])
    result = calculate_llm_kpis(req, tenant)
    assert result["estimated_cost_usd"] is None
    assert result["cost_coverage"] == 0.5


def test_extreme_finite_latency_percentiles_remain_finite():
    tenant = uuid4()
    req = request(tenant, observations=[
        {"status": "ok", "latency_ms": 1e308, "ttft_ms": 1e308},
        {"status": "ok", "latency_ms": 1e308, "ttft_ms": 1e308},
    ])
    result = calculate_llm_kpis(req, tenant)
    assert result["latency_p50_ms"] == 1e308
    assert result["latency_p95_ms"] == 1e308
    assert result["latency_p99_ms"] == 1e308
    assert result["ttft_p95_ms"] == 1e308


@pytest.mark.parametrize("invalid_status", [
    "ok\n", "error\n", "degraded\n", "OK", "ok ", "unknown", "",
])
def test_llm_observation_status_requires_exact_enum(invalid_status):
    tenant = uuid4()
    with pytest.raises(ValidationError):
        request(tenant, observations=[{"status": invalid_status, "latency_ms": 100}])


def test_llm_status_counts_cover_all_samples_exactly():
    tenant = uuid4()
    req = request(tenant, observations=[
        {"status": "ok", "latency_ms": 100},
        {"status": "error", "latency_ms": 120},
        {"status": "degraded", "latency_ms": 140},
    ])
    result = calculate_llm_kpis(req, tenant)
    assert result["success_rate_pct"] == pytest.approx(100 / 3, abs=0.001)
    assert result["error_rate_pct"] == pytest.approx(100 / 3, abs=0.001)
    assert result["degraded_rate_pct"] == pytest.approx(100 / 3, abs=0.001)


@pytest.mark.parametrize("invalid_model", [
    "provider/model\n", "provider/model\r\n", "provider/model ",
    " provider/model", "provider/model\u200b", "provider//model\n",
])
def test_model_identity_rejects_trailing_newlines_and_invisible_characters(invalid_model):
    with pytest.raises(ValidationError):
        request(uuid4(), model_id=invalid_model)


def test_model_identity_accepts_namespaced_provider_and_version():
    tenant = uuid4()
    result = calculate_llm_kpis(
        request(tenant, model_id="provider/model-v2:2026.11"), tenant
    )
    assert result["model_id"] == "provider/model-v2:2026.11"


def test_kpi_response_exposes_exact_missing_measurement_counts():
    tenant = uuid4()
    req = request(tenant, observations=[
        {"status": "ok", "latency_ms": 100, "input_tokens": 10, "tps": 40},
        {"status": "error", "ttft_ms": 20, "output_tokens": 5,
         "estimated_cost_usd": 0.01},
    ])
    result = calculate_llm_kpis(req, tenant)
    for metric in ("latency_ms", "ttft_ms", "tps", "estimated_cost_usd",
                   "input_tokens", "output_tokens"):
        assert result["measurement_coverage"][metric] == {
            "measured": 1, "missing": 1, "total": 2
        }
    assert result["sample_window_state"] == "UNVERIFIED"
    assert result["sample_provenance_state"] == "UNVERIFIED"
    assert result["authoritative"] is False


@pytest.mark.parametrize("anomalies,processed,expected_state", [
    (None, None, "MISSING"),
    (2, None, "MISSING"),
    (None, 20, "MISSING"),
    (0, 0, "ZERO_DENOMINATOR"),
    (0, 20, "CALLER_SUPPLIED_UNVERIFIED"),
])
def test_sentinel_counter_quality_state(anomalies, processed, expected_state):
    tenant = uuid4()
    req = request(
        tenant,
        sentinel_anomalies_total=anomalies,
        sentinel_events_processed_total=processed,
    )
    result = calculate_llm_kpis(req, tenant)
    assert result["sentinel_counter_state"] == expected_state
    assert result["sentinel_counter_coverage"] == {
        "anomalies_present": anomalies is not None,
        "events_processed_present": processed is not None,
    }
    if expected_state != "CALLER_SUPPLIED_UNVERIFIED":
        assert result["sentinel_anomaly_rate_pct"] is None
    else:
        assert result["sentinel_anomaly_rate_pct"] == 0
        assert result["authoritative"] is False


def test_tiny_nonzero_sentinel_rate_preserves_exact_fraction():
    tenant = uuid4()
    result = calculate_llm_kpis(request(
        tenant,
        sentinel_anomalies_total=1,
        sentinel_events_processed_total=1_000_000,
    ), tenant)
    assert result["sentinel_anomaly_rate_pct"] == 0
    assert result["sentinel_anomaly_rate_ratio"] == {
        "numerator": 1, "denominator": 1_000_000,
    }
    assert result["sentinel_counter_state"] == "CALLER_SUPPLIED_UNVERIFIED"


@pytest.mark.parametrize("anomalies,processed", [
    (None, None), (1, None), (None, 10), (0, 0),
])
def test_unknown_sentinel_rate_never_exposes_false_fraction(anomalies, processed):
    tenant = uuid4()
    result = calculate_llm_kpis(request(
        tenant,
        sentinel_anomalies_total=anomalies,
        sentinel_events_processed_total=processed,
    ), tenant)
    assert result["sentinel_anomaly_rate_ratio"] is None


@pytest.mark.parametrize("field", [
    "sentinel_anomalies_total", "sentinel_events_processed_total",
])
@pytest.mark.parametrize("invalid", [
    -1, 9223372036854775808, 1.0, True, "1",
])
def test_sentinel_counters_require_bounded_exact_integers(field, invalid):
    tenant = uuid4()
    overrides = {
        "sentinel_anomalies_total": None,
        "sentinel_events_processed_total": None,
        field: invalid,
    }
    with pytest.raises(ValidationError):
        request(tenant, **overrides)


def test_sentinel_counter_accepts_signed_bigint_maximum():
    tenant = uuid4()
    limit = 9223372036854775807
    result = calculate_llm_kpis(request(
        tenant,
        sentinel_anomalies_total=limit,
        sentinel_events_processed_total=limit,
    ), tenant)
    assert result["sentinel_anomaly_rate_ratio"] == {
        "numerator": limit, "denominator": limit,
    }
    assert result["sentinel_anomaly_rate_pct"] == 100
