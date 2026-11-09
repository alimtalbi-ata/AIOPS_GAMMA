# Three-repository selection and implementation register

Static source review on 2026-11-09. This is not runtime integration certification.

## 1. `alimtalbi-ata/aiops`: operational control plane

**Retain** the canonical Core incident/Run state machine, Temporal/Worker durable orchestration, Evidence provenance, Policy fail-closed checks, CMDB/GLPI ITSM links and Digital Twin. Source inspected: `app/core/main.py`, `app/policy/main.py`, `app/evidence/main.py`, `app/portal/noc_correlation.py`, `app/shared/tenant_scope.py`.

**Adapted in Gamma:** conservative impact and tenant-scope helpers, advisory remediation policy preview, canonical run projection, deterministic source-event deduplication. **Do not duplicate:** Core's authoritative Run writer, Temporal scheduler, GLPI credentials, Policy's approval gate or LIVE executor. Existing Core source has endpoints without independently qualified per-tenant ACL; Gamma must not expose them to the frontend.

## 2. `alimtalbi-ata/observability-stack`: telemetry data plane

**Use upstream services:** OpenTelemetry Collector, Data Prepper, OpenSearch for logs/traces, Prometheus/Cortex for metrics and alerting, Dashboards for APM/Application Map. Source inspected: README and documented component architecture. Existing Gamma OpenSearch query adapter remains behind a feature flag. Reuse configuration and protocol conventions; do not vendor or launch a competing OpenSearch stack or copy demo credentials. Verify index mappings, TLS, tenant isolation, index policies and cross-signal IDs against a running deployment before activation.

## 3. `alimtalbi-ata/aurora`: investigation UX and agent patterns

**Adapt concepts:** evidence-linked incident timeline, recurrence grouping, analyst/critic hypothesis flow, bounded read-only investigation tools, postmortem templates, structured proposed fixes. Source inspected: README and prior redaction source analysis. The original codebase uses Flask/Celery/LangGraph, Memgraph and Kubernetes sandbox pods; copying its runtime wholesale would create a second control plane, so Gamma keeps FastAPI/PostgreSQL and integrates only qualified adapters. Preserve Apache-2.0 attribution for any actual copied code; avoid unreviewed transitive dependencies.

## Delivered this slice

- `app/reused/correlation.py`: deterministic, bounded **read-only** correlation of source events by service/CI, symptom and time window, including duplicate suppression and provenance references.
- `POST /api/v1/incidents/correlation/preview`: authenticated internal API, never creates Core incidents or ITSM tickets and never authorizes LIVE effects.
- `tests/test_correlation.py`: duplication, grouping, time window, tenant isolation, bounds, unknown RCA/CMDB, and no-execution assertions.

## Next integration gates

1. Deploy a trusted identity gateway that resolves tenant from authenticated identity, with tenant-specific Core/Evidence/Twin authorization. Do not trust arbitrary browser `X-Tenant-Id`.
2. Qualify fixed-origin read-only Core/Evidence/Twin adapters with explicit auth, bounded JSON, no redirects and failure tests.
3. Confirm OpenSearch Data Prepper index mappings and Cortex tenant-scoped PromQL adapter.
4. Implement persistent incident grouping and idempotent Core/ITSM reconciliation through existing canonical services, not parallel database writes.
5. Evaluate evidence-grounded RCA on replay cases, with critic, source citations and UNKNOWN outcomes.
6. Version and approve runbooks, independent policy evaluation, dry-run, HITL, and audited one-time execution receipts before LIVE.
