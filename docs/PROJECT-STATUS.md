# AIOPS_GAMMA — Project status and decision record

Updated: 2026-11-09. This file is the durable starting point for every contributor or future assistant session. **Status is a snapshot, not an automatically updated dashboard.**

## Mission
Build an AI Site Reliability Engineer (AI SRE): observe, predict, normalize, deduplicate, correlate, map impacted assets, open/reconcile ITSM, investigate evidence-based root causes, propose approved runbooks, execute only under deterministic enterprise policy and independently verified authorization, verify recovery and learn.

## Canonical repositories
- Gamma: https://github.com/alimtalbi-ata/AIOPS_GAMMA
- Existing control plane: https://github.com/alimtalbi-ata/aiops
- Telemetry stack: https://github.com/alimtalbi-ata/observability-stack
- Investigation reference: https://github.com/alimtalbi-ata/aurora

## Code baseline
- Development branch: `feat/observability-foundation`, draft PR #1; **not merged to main**.
- Backend: FastAPI, SQLAlchemy/PostgreSQL, tenant-filtered optional OpenSearch log search, inbox/outbox, CMDB service bindings, evidence cache, relay, Alembic migration, read-only impact/correlation previews, advisory policy preview.
- Frontend: React/TypeScript observability console, synthetic demo content; **not authenticated production data**.
- Deployment: Docker Compose dev stack; optional demo OpenSearch, feature flags default off. Existing upstream telemetry deployment is not provisioned or validated by Gamma.
- CI: Python tests + frontend build. GitHub Actions **Python checks** passed for `73ab1335` (run `42679137227`, 2026-11-09). Subsequent documentation commits require their own HEAD CI verification; frontend and staging qualification must be evaluated separately.

## Capability matrix

| Capability | Status | Evidence / gap |
|---|---|---|
| Console visual prototype | Prototype | React, synthetic examples only |
| Alert ingestion + idempotent inbox/outbox | Prototype | PG models/API; live integration and delivery contract unqualified |
| Log query | Feature-flagged prototype | Query DSL tenant filter; no verified OpenSearch DLS/production index mappings |
| Metrics and traces end-to-end | Not integrated | General PromQL metrics endpoint intentionally returns 501; no qualified Cortex/OTel connection |\n| LLM KPI preview (Sentinel/ArgusLM) | Implemented, non-authoritative | Strict tenant-bound caller-supplied samples; P50/P95/P99, TTFT, throughput, cost estimate, anomalies; **no live connectors, storage or dashboard** |
| Correlation/deduplication | Read-only preview | Exact source IDs, symptom/service/CI/time; no durable incident clustering |
| CMDB impact | Unverified estimate | No live Twin/GLPI authority validation |
| Canonical Core/Temporal | Existing in `aiops`, not connected | Read-only authenticated adapters pending |
| ITSM ticket sync | Advisory preview only | Enterprise priority matrix and idempotency proposal; no ticket mutation |\n| GLPI incident snapshots | Disabled-by-default prototype | HTTPS GET-only, tenant/entity checks, bounded body, no-store; staging API/RBAC not qualified |
| RCA AI/Critic | Not integrated | Evidence model and conceptual design only |
| Policy | Advisory preview | **Never grants LIVE execution** |
| Autonomous remediation | Not implemented | Requires independent policy/HITL, approved recipes, fencing, audit, rollback, verification |
| Production security | Not qualified | Gateway identity, per-tenant ACL, OIDC/mTLS, secret handling, DLS needed |

## Hard architectural decisions
1. Existing `aiops` Core is the authoritative incident/run lifecycle owner. Gamma never directly mutates Core DB.
2. Existing Policy and Temporal/Worker are the only qualified future execution path. LLM suggestions cannot authorize actions.
3. OpenSearch is logs/traces search; existing Cortex/Prometheus remains metrics authority.
4. Aurora provides investigation patterns and possible adapters, **not** a second unbounded execution control plane.
5. Tenant identity must come from independently authenticated and authorized gateway, not browser-controlled headers.
6. Fail closed on missing evidence, missing authorization, stale topology, unsupported mapping, or missing runbook.
7. Synthetic demo data is explicitly labelled; never present it as real monitoring.

## Tracking workflow
- GitHub Issues = actionable backlog with acceptance criteria and verification.
- GitHub PRs = implementation and review, linking issue via `Refs #N` (only use `Closes #N` when acceptance criteria truly met).
- `docs/HANDOVER.md` = restart checklist and current blockers.
- `docs/ROADMAP.md` = milestone sequencing, dependencies, release gates.
- `docs/DECISIONS.md` = architecture decision history.
- `docs/OPERATIONS.md` = developer setup and operational safety.
- Update this file and HANDOVER in every substantive PR; never silently claim untested integrations.

## Release bar
No production claim without a real multi-tenant isolation test, replay/duplicate tests, fault injection, ITSM idempotency, runbook allowlist, HITL receipt binding, rollback qualification, and full audit trail.

## Reference-only SRE/AI DevOps catalogs (2026-11-09)

Added [docs/SRE-REFERENTIALS.md](SRE-REFERENTIALS.md) based on two curated user-provided GitHub directories. This adds a **selection and review process only**; zero third-party skills/agents/MCP servers installed, no changed execution privileges, and no external integrations qualified. Follow up in #2–#6.

## Canonical read adapter prototype (2026-11-09)

A new feature-flagged, fail-closed HTTPS GET snapshot adapter is available for Core/Evidence/Twin with strict resource allowlist, 256 KiB maximum response, timeout, no redirects, and required tenant-id echo. **Not a production-qualified integration:** upstream paths/tenant ACL/OIDC/mTLS/network egress are unverified; flag remains OFF. See [CANONICAL-READ-ADAPTER](CANONICAL-READ-ADAPTER.md) and issue #2.

## ITIL 4 enterprise architecture (2026-11-09)
Added `docs/ITIL4-GOVERNANCE.md` and a typed, authenticated **preview-only** ITIL incident/problem/change/CI workflow projection. No ITSM tickets, problem records, RFCs or CMDB mutations are performed; enterprise-specific ITSM rules and change authority must be qualified.

## ITSM synchronization proposal (2026-11-09)
- New [ITSM-SYNC-CONTRACT](ITSM-SYNC-CONTRACT.md) describes enterprise-owned priority matrices and safe incident sync proposals with stable logical idempotency keys.
- Implemented as a **pure internal preview** only; not a vendor connector, not a durable exactly-once guarantee, and no ITSM writes.


## Latest GLPI and KPI delivery snapshot (2026-11-09)

- **GLPI:** [GLPI-READ-ADAPTER](GLPI-READ-ADAPTER.md) implements a single-tenant, entity-bound read-only incident snapshot behind a feature flag (off by default). Regression tests cover missing configuration, tenant denial, invalid URL/port, upstream redirects/errors, oversized or malformed responses and cache policy. [GLPI-STAGING-QUALIFICATION](GLPI-STAGING-QUALIFICATION.md) is a **test plan only**, not executed proof. The ITSM incident sync remains [preview-only](ITSM-SYNC-CONTRACT.md).
- **LLM KPI:** reviewed `alimtalbi-ata/sentinel-llm` and `alimtalbi-ata/arguslm-llm`; implemented `app/reused/llm_kpi.py` and `POST /api/v1/observability/llm/kpis/preview` with strict input validation, tenant equality and unit-labelled KPI projections. See [LLM-KPI-CONTRACT](LLM-KPI-CONTRACT.md). These are **caller-supplied preview samples**, not trusted production observations.
- **Validation:** Python checks passed on `73ab1335` ([run 42679137227](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/42679137227)). New documentation HEAD CI and all real upstream staging tests remain to be confirmed.
- **Immediate next gate:** trusted source-specific tenant/model ACL mapping, fixed-origin read-only data retrieval, timestamped metric provenance and sample coverage, then SLO/dashboard qualification. No autonomous remediation or ITSM writes.

## Evidence-linked investigation preview (2026-11-09)

Implemented `app/reused/investigation.py` and `POST /api/v1/incidents/investigation/preview` with tenant equality, bounded typed evidence, UTC-aware timestamps, hypothesis citation integrity and non-authoritative output. Tests cover cross-tenant denial, missing references, conflicting citations and unknowns. This is **not** an autonomous investigation agent or a verified RCA; no external evidence is retrieved. See [INVESTIGATION-PREVIEW](INVESTIGATION-PREVIEW.md). New HEAD CI pending.
