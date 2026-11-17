# LLM KPI measurement contract — Sentinel + ArgusLM

**Status:** first implementation is a validated-shape, non-authoritative **preview** endpoint, not an operational telemetry connector.

## Reviewed code sources

- [sentinel-llm](https://github.com/alimtalbi-ata/sentinel-llm), `main`: `crates/sentinel-core/src/metrics.rs` defines ingestion, anomaly and alert counters, LLM latency/token/cost histograms; `crates/sentinel-api/src/handlers/metrics.rs` exposes a Prometheus text endpoint; `deployments/prometheus.yml` scrapes `/metrics`. Dashboards and alert rules exist in the repository, but have **not** been run or API-qualified here.
- [arguslm-llm](https://github.com/alimtalbi-ata/arguslm-llm), `master`: `arguslm/server/core/metrics.py` calculates TTFT, throughput and model-price-based estimated cost; `arguslm/server/api/monitoring.py` provides historical uptime checks; benchmark results include latency, TTFT, throughput, tokens, cost and error. Static price mappings are **not** billing records; they require versioning and validation.
- AIOPS_GAMMA keeps canonical incident/ITSM ownership separate from AI-observability telemetry. No source repository was copied or deployed.

## First API

`POST /api/v1/observability/llm/kpis/preview`: requires the trusted internal gateway credentials and tenant identity; the request's tenant UUID must match the authenticated principal. Body is a strict, bounded list of 1–1000 typed request observations plus optional Sentinel anomaly/processed counters. Unknown keys (including raw prompts/responses) are rejected. It does not call Sentinel/ArgusLM, start benchmarks, trigger inference, write to GLPI or persist metrics.

| KPI | Definition | Unit | Source provenance |
| --- | --- | --- | --- |
| Request success rate | status=ok / all sampled requests | % | ArgusLM uptime/benchmark statuses; preview status policy |
| Request error rate | status=error / all sampled requests | % | ArgusLM |
| Latency P50/P95/P99 | linearly interpolated nearest adjacent order statistics | milliseconds | ArgusLM `total_latency_ms` / Sentinel latency observations |
| TTFT P95 | time to first **content** token | milliseconds | ArgusLM `ttft_ms` |
| Mean generation throughput | mean of observed per-request `tps` | tokens/second | ArgusLM `tps` (including TTFT) |
| Total input/output tokens | sum, only when at least one sample contains token counts | tokens | ArgusLM counters |
| Estimated cost | sum only if **every** observation has a cost estimate | USD estimated | ArgusLM cost estimates |
| Cost coverage | observations with cost estimates / all observations | fraction 0–1 | Preview completeness |
| Sentinel anomaly rate | anomalies / processed events when denominator > 0 | % | Sentinel cumulative counters **for an aligned single scope and time window** |

**Caveat:** Sentinel counters are cumulative and may reset on restart; delta/rate needs temporally aligned samples and counter-reset handling. For now the preview assumes the caller provides meaningful, aligned counts; output is flagged `authoritative=false`. Never combine unrelated model/tenant scopes; no multi-model or cross-tenant comparison is approved.

Missing values are `null`, never estimated as 0. Cost is `null` for partial coverage. P95/P99 over small samples are technically calculable but **not statistically stable**; dashboards must show sample size and data freshness before any SLO decision. `degraded` counts in neither success nor error rate and remains included in the request denominator.

## Example preview contract

Request (synthetic example; never send raw prompts or responses):

```json
{
  "tenant_id": "00000000-0000-0000-0000-000000000001",
  "model_id": "demo/model",
  "observations": [
    {"status": "ok", "latency_ms": 100, "ttft_ms": 20, "tps": 50, "input_tokens": 10, "output_tokens": 5, "estimated_cost_usd": 0.01},
    {"status": "error", "latency_ms": 300, "ttft_ms": 60, "tps": 0, "input_tokens": 20, "output_tokens": 0, "estimated_cost_usd": 0.02}
  ],
  "sentinel_anomalies_total": 2,
  "sentinel_events_processed_total": 20
}
```

Expected selected fields: `sample_count=2`, `success_rate_pct=50`, `error_rate_pct=50`, `latency_p50_ms=200`, `latency_p95_ms=290`, `ttft_p95_ms=58`, `mean_tps=25`, `estimated_cost_usd=0.03`, `cost_coverage=1`, `sentinel_anomaly_rate_pct=10`. The output includes `data_source="caller_supplied_preview"`, `authoritative=false`, and `production_qualified=false`.

**API safety:** `X-Internal-Api-Key` and `X-Tenant-Id` must be set by a trusted internal gateway. A different `tenant_id` in the request is rejected; no inference should be made about another tenant. The model identifier is only syntactically validated at this stage, **not** independently authorized against an external model registry. Maximum 1,000 observations per request. Non-finite/negative measurements, TTFT exceeding latency, invalid status and unknown fields are rejected. The preview does not enforce a common timestamp/window or verify the authenticity of Sentinel counters.

**Measurement caveats:** The current `total_input_tokens`/`total_output_tokens` sum known values when at least one sample provides a count; this is a **partial observed sum**, not a complete workload total when coverage is incomplete. `mean_tps` is an unweighted arithmetic mean of observed request-level throughput, not total tokens divided by wall-clock duration. `success_rate_pct + error_rate_pct` may be below 100% because degraded samples are in the denominator. Do not derive an uptime SLA from these preview statuses.

## Next integration steps and acceptance gates
1. Establish authenticated **server-side** source bindings and tenant-scoped Prometheus/Cortex query APIs for Sentinel. Validate actual metric names, Prometheus histogram units and counter resets; do not scrape raw cross-tenant `/metrics` from browsers.
2. Build a trusted read-only ArgusLM connector returning a whitelisted metric projection; require tenant mapping and model ACLs (ArgusLM monitoring API shown here is not tenant scoped).
3. Persist immutable timestamped measurement facts with provider/model/tenant identity, source watermark, lineage, quality flags, retention and idempotency. Query per time window; calculate SLOs and alert burn rates only from qualified history.
4. Add server-owned SLO budgets (availability, P95 latency, TTFT, model cost) and distinguish estimated USD from billed USD. Review accuracy and gap behavior with service owners.
5. Instrument end-to-end dashboards and test staged upstream failures, drift, authorization, privacy and real sample volume. Do not authorize autonomous remediation from KPI excursions.

No production measurements, live integration tests or KPI dashboards have been executed by this change.
