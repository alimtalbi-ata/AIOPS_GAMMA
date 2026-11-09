# Engineering review: Akmatori SRE + IncidentFox SRE

Date: 2026-11-09. Sources reviewed at the **main** revisions below. This is static source inspection; no operational or license certification has been performed.

## 1. Source and license boundaries

| Source | Tree SHA | License | Result |
|---|---|---|---|
| https://github.com/alimtalbi-ata/akmatori-sre | `8691dc9420e9e2079a3c1d4196296d8c13c7c2d8` | Apache-2.0 root LICENSE | Study and independent Python adaptation of webhook normalization; do not vendor Go runtime |
| https://github.com/alimtalbi-ata/incidentfox-sre | check main branch revision at next update | Mixed: core Apache-2.0, designated production security files BUSL-1.1 | Study anomaly/RCA/postmortem patterns only; **do not copy BUSL files** |

IncidentFox `LICENSING.md` expressly identifies `sre-agent/sandbox_manager.py`, `sandbox_server.py`, `credential-proxy/`, `sandbox-router/` and `sre-agent/Dockerfile` as Business Source License 1.1 security layer. Independently obtain a license and verify upstream restrictions before considering those packages in production.

## 2. Akmatori components assessed

- `internal/alerts/adapters/alertmanager.go` and `grafana.go`: multilevel webhook envelope, per-alert fingerprint, labels, status and timestamps; **selected** for Gamma's pure normalization prototype.
- `internal/alerts/adapters/pagerduty.go`, `datadog.go`, `zabbix.go`: **candidate** adapters to implement only after schema samples and authentication tests.
- `internal/handlers/correlation_gate.go`: demonstrates the concurrent-arrival double-incident problem; **do not reuse** its global in-process gate (time-out can bypass it). Prefer database uniqueness, idempotent outbox and distributed per-tenant/incident serialization in Core.
- `internal/services/proposal_service.go`: versioned/snapshotted changes and stale-approval rejection; **candidate** for approved *configuration/runbook* proposals, not authorization to execute on production.
- `internal/services/memory_evidence.go` and `incident_memory_extractor.go`: **candidate** evidence-backed memory extraction, review and freshness controls. Existing Gamma/AIOps Evidence Center remains canonical.
- `mcp-gateway/internal/tools/` and `agent-worker/src/script-executor.ts`: **excluded** from direct integration pending sandbox/tenant/RBAC and command allowlist review. No imported executor.

## 3. IncidentFox components assessed

- `local/claude_code_pack/mcp-servers/incidentfox/src/incidentfox_mcp/tools/anomaly.py`: metric anomaly, change-point, forecasting categories; **selected** bounded independent median/MAD preview. No auto-incident writes or claims of causal inference.
- `.../tools/blast_radius.py`: dependency traversal ideas; candidate only. Do not let unverified source graph imply owner/impact; use Twin/CMDB as authority.
- `config_service/golden_templates/09_incident_postmortem/postmortem_writer.md`: evidence-first, timestamped and blameless postmortem structure; candidate for Gamma RCA reporting after source validation.
- `sre-agent/.claude/skills/metrics-analysis/scripts/query_prometheus.py`: optional typed/read-only Cortex query approach; Gamma must build PromQL with tenant-scoped safe templates, never execute raw generated queries.
- README lists multi-agent, RAG knowledge base, Slack-first response and correlation. These are product concepts, not independently verified installed capabilities.
- Production security files listed in `LICENSING.md`: **strictly excluded** from copy/reuse due BUSL license.

## 4. Delivered in Gamma

- `app/reused/alertmanager.py`: pure, bounded, schema-validated Alertmanager/Grafana event normalizer; stable per-source event hashes and status transitions; no arbitrary webhook endpoint/secret handling or external requests.
- `app/reused/anomaly.py`: bounded robust median/MAD anomaly preview with finite sample validation and UNKNOWN state for constant baseline; **not seasonality-aware forecasting or validated detection accuracy**.
- `POST /api/v1/investigation/alerts/normalize-preview` and `POST /api/v1/investigation/metrics/anomaly-preview`: internal-authenticated preview endpoints with no storage or LIVE effect.
- Unit tests, source register and durable handover. These endpoints are **not** webhook receivers.

## 5. Operational qualification gates

1. Authenticate sources and resolve tenant from the trusted gateway; signed source data is not an ACL.
2. Reconcile event IDs/status, source clock skew and replay semantics with Core; fix out-of-order lifecycle cases before persistence.
3. Enforce per-connector authorization, egress allowlist, timeouts, capacity and secrets management.
4. Validate statistical anomaly detection against real baselines, seasonality and false-positive metrics, with human review.
5. Audit independent security policy/HITL, one-use receipts, approved runbooks and rollback before any remediation.
6. Reassess third-party licenses at pinned revisions; never vendor IncidentFox BUSL security code.

## Backlog

- #3: OTel, OpenSearch, Cortex and typed alert connectors.
- #4: persistent correlation and lifecycle / ITSM.
- #5: analyst/critic, anomaly assessment and postmortem.
- #6: runbook proposals and governed remediation.
