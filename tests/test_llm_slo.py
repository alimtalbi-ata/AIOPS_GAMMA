"""UC07: advisory LLM SLO preview, no production qualification."""
from datetime import datetime, timedelta, timezone
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


def test_slo_route_requires_signed_gateway_principal_and_prevents_caching(monkeypatch):
    import base64
    import hashlib
    import hmac
    import json
    import time

    from fastapi.testclient import TestClient
    from app.main import app
    from app.settings import settings

    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    monkeypatch.setattr(settings, "gateway_assertion_secret", "s" * 48)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "trusted-gateway")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-api")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok", "latency_ms": 150},
    ])
    path = "/api/v1/observability/llm/slo/preview"
    issued = int(time.time())
    claims = {
        "iss": "trusted-gateway", "aud": "gamma-api",
        "sub": "user:123", "actor_type": "user",
        "tenant_id": str(tenant), "tenant_access": True,
        "iat": issued, "exp": issued + 30, "jti": "slo-test-assertion",
        "method": "POST", "path": path,
    }
    def b64(raw):
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    encoded = b64(json.dumps(claims, separators=(",", ":")).encode())
    signature = b64(hmac.new(b"s" * 48, encoded.encode(), hashlib.sha256).digest())
    headers = {
        "X-Internal-Api-Key": "test-secret",
        "X-Gateway-Principal": encoded + "." + signature,
    }
    with TestClient(app) as client:
        denied = client.post(path, json=req.model_dump(mode="json"))
        unsigned = client.post(
            path, json=req.model_dump(mode="json"),
            headers={"X-Internal-Api-Key": "test-secret",
                     "X-Tenant-Id": str(tenant)},
        )
        allowed = client.post(path, json=req.model_dump(mode="json"), headers=headers)
        forged = client.post(
            path, json=req.model_dump(mode="json"),
            headers={**headers, "X-Tenant-Id": str(uuid4())},
        )
    assert denied.status_code == 401
    assert unsigned.status_code == 401
    assert allowed.status_code == 200
    assert allowed.headers["cache-control"] == "no-store"
    assert allowed.json()["state"] == "PASS_PREVIEW"
    # X-Tenant-ID cannot override the signed tenant identity.
    assert forged.status_code == 200
    assert forged.json()["tenant_id"] == str(tenant)


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


def test_configured_coverage_threshold_cannot_certify_biased_partial_p95():
    tenant = uuid4()
    observations = [{"status": "ok", "latency_ms": 100} for _ in range(19)]
    observations.append({"status": "ok"})
    req = make_request(tenant, observations, min_latency_coverage=0.90)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["checks"]["latency_coverage"]["passed"] is True
    assert result["latency_complete"] is False
    assert result["state"] == "INSUFFICIENT_DATA"
    assert result["observed_breaches"] == []


def test_complete_latency_samples_can_pass_when_configured_coverage_is_lower():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok", "latency_ms": 150},
    ], min_latency_coverage=0.5)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["latency_complete"] is True
    assert result["state"] == "PASS_PREVIEW"


def test_insufficient_data_reasons_are_specific_and_stable():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok"},
    ], min_samples=3)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "INSUFFICIENT_DATA"
    assert result["insufficient_data_reasons"] == [
        "sample_count_below_minimum",
        "latency_coverage_below_minimum",
        "latency_measurements_incomplete",
    ]


def test_coverage_threshold_met_but_missing_measurement_is_explained():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok"},
    ], min_latency_coverage=0.5)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "INSUFFICIENT_DATA"
    assert result["insufficient_data_reasons"] == [
        "latency_measurements_incomplete",
    ]


def test_complete_pass_has_no_insufficient_data_reasons():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok", "latency_ms": 120},
    ])
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "PASS_PREVIEW"
    assert result["insufficient_data_reasons"] == []


def test_optional_ttft_slo_passes_with_complete_measurements():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 120, "ttft_ms": 30},
        {"status": "ok", "latency_ms": 140, "ttft_ms": 50},
    ], max_ttft_p95_ms=60)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "PASS_PREVIEW"
    assert result["ttft_complete"] is True
    assert result["checks"]["ttft_p95_ms"]["enabled"] is True
    assert result["checks"]["ttft_p95_ms"]["passed"] is True


def test_optional_ttft_slo_reports_breach():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 120, "ttft_ms": 30},
        {"status": "ok", "latency_ms": 140, "ttft_ms": 100},
    ], max_ttft_p95_ms=60)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "BREACH_PREVIEW"
    assert result["observed_breaches"] == ["ttft_p95_ms"]


def test_optional_ttft_slo_cannot_pass_with_missing_ttft():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 120, "ttft_ms": 30},
        {"status": "ok", "latency_ms": 140},
    ], max_ttft_p95_ms=60)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "INSUFFICIENT_DATA"
    assert result["ttft_complete"] is False
    assert result["insufficient_data_reasons"] == ["ttft_measurements_incomplete"]


def test_ttft_slo_disabled_does_not_require_ttft_measurements():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 120},
        {"status": "ok", "latency_ms": 140},
    ])
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "PASS_PREVIEW"
    assert result["ttft_complete"] is None
    assert result["checks"]["ttft_p95_ms"]["enabled"] is False


def test_invalid_ttft_slo_threshold_rejected():
    tenant = uuid4()
    for invalid in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            make_request(tenant, [{"status": "ok"}], max_ttft_p95_ms=invalid)


def test_optional_throughput_slo_passes_with_complete_measurements():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 120, "tps": 30},
        {"status": "ok", "latency_ms": 140, "tps": 50},
    ], min_throughput_tps=40)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "PASS_PREVIEW"
    assert result["throughput_complete"] is True
    assert result["checks"]["mean_tps"]["passed"] is True


def test_optional_throughput_slo_reports_breach():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 120, "tps": 20},
        {"status": "ok", "latency_ms": 140, "tps": 30},
    ], min_throughput_tps=40)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "BREACH_PREVIEW"
    assert result["observed_breaches"] == ["mean_tps"]


def test_missing_throughput_cannot_certify_optional_slo():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 120, "tps": 60},
        {"status": "ok", "latency_ms": 140},
    ], min_throughput_tps=40)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "INSUFFICIENT_DATA"
    assert result["insufficient_data_reasons"] == ["throughput_measurements_incomplete"]


def test_disabled_throughput_slo_does_not_require_tps():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 120},
        {"status": "ok", "latency_ms": 140},
    ])
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "PASS_PREVIEW"
    assert result["throughput_complete"] is None
    assert result["checks"]["mean_tps"]["enabled"] is False


@pytest.mark.parametrize("invalid", [0, -1, float("nan"), float("inf")])
def test_invalid_throughput_threshold_rejected(invalid):
    with pytest.raises(ValidationError):
        make_request(uuid4(), [{"status": "ok"}], min_throughput_tps=invalid)


def test_optional_mean_cost_budget_passes_with_complete_costs():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100, "estimated_cost_usd": 0.01},
        {"status": "ok", "latency_ms": 120, "estimated_cost_usd": 0.03},
    ], max_mean_cost_usd=0.02)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "PASS_PREVIEW"
    assert result["cost_complete"] is True
    assert result["checks"]["mean_cost_usd"]["passed"] is True


def test_optional_mean_cost_budget_breach_uses_unrounded_mean():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100, "estimated_cost_usd": 0.010001},
        {"status": "ok", "latency_ms": 120, "estimated_cost_usd": 0.010003},
    ], max_mean_cost_usd=0.010001)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "BREACH_PREVIEW"
    assert result["observed_breaches"] == ["mean_cost_usd"]


def test_optional_mean_cost_budget_requires_every_sample():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100, "estimated_cost_usd": 0.001},
        {"status": "ok", "latency_ms": 120},
    ], max_mean_cost_usd=0.02)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "INSUFFICIENT_DATA"
    assert result["insufficient_data_reasons"] == ["cost_measurements_incomplete"]
    assert result["cost_complete"] is False


def test_disabled_mean_cost_budget_does_not_require_costs():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok", "latency_ms": 120},
    ])
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "PASS_PREVIEW"
    assert result["cost_complete"] is None
    assert result["checks"]["mean_cost_usd"]["enabled"] is False


@pytest.mark.parametrize("invalid", [-1, float("nan"), float("inf")])
def test_invalid_cost_budget_rejected(invalid):
    with pytest.raises(ValidationError):
        make_request(uuid4(), [{"status": "ok"}], max_mean_cost_usd=invalid)


@pytest.mark.parametrize("field", ["tps", "estimated_cost_usd"])
def test_extreme_finite_measurements_keep_finite_mean_without_intermediate_overflow(field):
    tenant = uuid4()
    observations = [
        {"status": "ok", "latency_ms": 100, field: 1e308},
        {"status": "ok", "latency_ms": 120, field: 1e308},
    ]
    options = (
        {"min_throughput_tps": 40} if field == "tps"
        else {"max_mean_cost_usd": 0.02}
    )
    req = make_request(tenant, observations, **options)
    result = evaluate_llm_slo_preview(req, tenant)
    metric = "mean_tps" if field == "tps" else "mean_cost_usd"
    assert result["checks"][metric]["value"] == 1e308
    assert result["state"] == ("PASS_PREVIEW" if field == "tps" else "BREACH_PREVIEW")


def test_extreme_finite_p95_does_not_overflow_slo_response():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 1e308, "ttft_ms": 1e308},
        {"status": "ok", "latency_ms": 1e308, "ttft_ms": 1e308},
    ], max_ttft_p95_ms=200)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "BREACH_PREVIEW"
    assert result["checks"]["latency_p95_ms"]["value"] == 1e308
    assert result["checks"]["ttft_p95_ms"]["value"] == 1e308
    assert result["observed_breaches"] == ["latency_p95_ms", "ttft_p95_ms"]


def test_slo_cost_mean_is_valid_even_when_kpi_total_cost_would_overflow():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100, "estimated_cost_usd": 1e308},
        {"status": "ok", "latency_ms": 120, "estimated_cost_usd": 1e308},
    ], max_mean_cost_usd=0.02)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "BREACH_PREVIEW"
    assert result["checks"]["mean_cost_usd"]["value"] == 1e308
    assert result["observed_breaches"] == ["mean_cost_usd"]


def test_slo_still_rejects_cross_tenant_after_kpi_decoupling():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok", "latency_ms": 120},
    ])
    with pytest.raises(ValueError, match="Cross-tenant"):
        evaluate_llm_slo_preview(req, uuid4())


@pytest.mark.parametrize("metric,field,threshold", [
    ("latency_p95_ms", "latency_ms", {}),
    ("ttft_p95_ms", "ttft_ms", {"max_ttft_p95_ms": 200}),
    ("mean_tps", "tps", {"min_throughput_tps": 40}),
    ("mean_cost_usd", "estimated_cost_usd", {"max_mean_cost_usd": 0.02}),
])
def test_partial_metric_does_not_report_unverified_breach(metric, field, threshold):
    tenant = uuid4()
    first = {"status": "ok", "latency_ms": 100}
    second = {"status": "ok", "latency_ms": 120}
    if field == "latency_ms":
        first[field] = 500
        second.pop("latency_ms")
    elif field == "ttft_ms":
        first["latency_ms"] = 500
        first[field] = 400
    elif field == "tps":
        first[field] = 1
    else:
        first[field] = 10
    req = make_request(tenant, [first, second], **threshold)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "INSUFFICIENT_DATA"
    assert result["checks"][metric]["passed"] is None
    assert metric not in result["observed_breaches"]


def test_complete_metric_breach_is_reported_despite_other_incomplete_metrics():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "error", "latency_ms": 500, "ttft_ms": 400},
        {"status": "ok", "latency_ms": 120},
    ], max_ttft_p95_ms=200)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "INSUFFICIENT_DATA"
    assert result["checks"]["latency_p95_ms"]["passed"] is False
    assert result["checks"]["ttft_p95_ms"]["passed"] is None
    assert result["observed_breaches"] == ["success_rate_pct", "latency_p95_ms"]


def test_slo_response_exposes_all_measurement_denominators_and_unverified_origin():
    tenant = uuid4()
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100, "ttft_ms": 20, "tps": 50},
        {"status": "ok", "latency_ms": 120, "estimated_cost_usd": 0.01},
    ])
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["measurement_coverage"] == {
        "latency_ms": {"measured": 2, "missing": 0, "total": 2},
        "ttft_ms": {"measured": 1, "missing": 1, "total": 2},
        "tps": {"measured": 1, "missing": 1, "total": 2},
        "estimated_cost_usd": {"measured": 1, "missing": 1, "total": 2},
    }
    assert result["sample_window_state"] == "UNVERIFIED"
    assert result["sample_provenance_state"] == "UNVERIFIED"
    assert result["authoritative"] is False
    assert result["live_remediation_authorized"] is False


def test_declared_window_is_bounded_and_still_not_authoritative():
    tenant = uuid4()
    end = datetime.now(timezone.utc) - timedelta(minutes=1)
    start = end - timedelta(hours=1)
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100, "observed_at": start},
        {"status": "ok", "latency_ms": 120,
         "observed_at": end - timedelta(seconds=1)},
    ], window_start=start, window_end=end)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "PASS_PREVIEW"
    assert result["sample_window_state"] == "CALLER_DECLARED_UNVERIFIED"
    assert result["declared_window"]["end_exclusive"] is True
    assert result["sample_provenance_state"] == "UNVERIFIED"
    assert result["authoritative"] is False
    assert result["live_remediation_authorized"] is False


@pytest.mark.parametrize("offset_seconds", [-1, 3600])
def test_declared_window_rejects_off_window_observations(offset_seconds):
    tenant = uuid4()
    end = datetime.now(timezone.utc) - timedelta(minutes=1)
    start = end - timedelta(hours=1)
    with pytest.raises(ValidationError, match="outside the declared window"):
        make_request(tenant, [
            {"status": "ok", "latency_ms": 100,
             "observed_at": start + timedelta(seconds=offset_seconds)},
            {"status": "ok", "latency_ms": 120, "observed_at": start},
        ], window_start=start, window_end=end)


def test_declared_window_requires_all_observation_timestamps():
    tenant = uuid4()
    end = datetime.now(timezone.utc) - timedelta(minutes=1)
    with pytest.raises(ValidationError, match="require timestamps"):
        make_request(tenant, [
            {"status": "ok", "latency_ms": 100},
            {"status": "ok", "latency_ms": 120, "observed_at": end - timedelta(minutes=2)},
        ], window_start=end - timedelta(hours=1), window_end=end)


def test_declared_window_rejects_partial_naive_future_or_oversized_bounds():
    tenant = uuid4()
    now = datetime.now(timezone.utc)
    rows = [{"status": "ok", "latency_ms": 100}] * 2
    cases = [
        {"window_start": now - timedelta(hours=1)},
        {"window_start": now.replace(tzinfo=None) - timedelta(hours=1),
         "window_end": now},
        {"window_start": now - timedelta(hours=25), "window_end": now},
        {"window_start": now, "window_end": now},
        {"window_start": now, "window_end": now + timedelta(hours=1)},
    ]
    for options in cases:
        with pytest.raises(ValidationError):
            make_request(tenant, rows, **options)


def test_observation_timestamp_rejects_naive_datetime():
    tenant = uuid4()
    with pytest.raises(ValidationError, match="timezone"):
        make_request(tenant, [
            {"status": "ok", "latency_ms": 100, "observed_at": datetime(2026, 1, 1)},
            {"status": "ok", "latency_ms": 120},
        ])


@pytest.mark.parametrize("invalid_timestamp", [
    1760000000, 1760000000000, "1760000000", " 2026-01-01T00:00:00Z ",
])
def test_observation_rejects_ambiguous_epoch_and_padded_timestamps(invalid_timestamp):
    with pytest.raises(ValidationError):
        make_request(uuid4(), [
            {"status": "ok", "latency_ms": 100, "observed_at": invalid_timestamp},
            {"status": "ok", "latency_ms": 120},
        ])


@pytest.mark.parametrize("invalid_bound", [
    1760000000, 1760000000000, "1760000000", " 2026-01-01T00:00:00Z ",
])
def test_declared_window_rejects_ambiguous_boundaries(invalid_bound):
    tenant = uuid4()
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        make_request(tenant, [
            {"status": "ok", "latency_ms": 100},
            {"status": "ok", "latency_ms": 120},
        ], window_start=invalid_bound, window_end=now)


def test_declared_window_accepts_explicit_iso8601_offset_strings():
    tenant = uuid4()
    end = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=1)
    start = end - timedelta(minutes=10)
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100,
         "observed_at": start.isoformat()},
        {"status": "ok", "latency_ms": 120,
         "observed_at": (end - timedelta(seconds=1)).isoformat()},
    ], window_start=start.isoformat(), window_end=end.isoformat())
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["state"] == "PASS_PREVIEW"
    assert result["sample_window_state"] == "CALLER_DECLARED_UNVERIFIED"


def test_declared_window_exposes_actual_sample_span_without_attestation():
    tenant = uuid4()
    end = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=1)
    start = end - timedelta(hours=1)
    first = start + timedelta(minutes=20)
    last = start + timedelta(minutes=40)
    req = make_request(tenant, [
        {"status": "ok", "latency_ms": 100, "observed_at": last},
        {"status": "ok", "latency_ms": 120, "observed_at": first},
    ], window_start=start, window_end=end)
    result = evaluate_llm_slo_preview(req, tenant)
    assert result["declared_window"] == {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "end_exclusive": True,
        "duration_seconds": 3600,
        "sample_count": 2,
        "first_observed_at": first.isoformat(),
        "last_observed_at": last.isoformat(),
    }
    assert result["sample_window_state"] == "CALLER_DECLARED_UNVERIFIED"
    assert result["authoritative"] is False


def test_legacy_slo_without_window_has_no_fabricated_sample_span():
    tenant = uuid4()
    result = evaluate_llm_slo_preview(make_request(tenant, [
        {"status": "ok", "latency_ms": 100},
        {"status": "ok", "latency_ms": 120},
    ]), tenant)
    assert result["declared_window"] is None
    assert result["sample_window_state"] == "UNVERIFIED"
