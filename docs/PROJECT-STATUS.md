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
- CI: Python tests + frontend build. GitHub Actions for commit `8235693a` reported success on 2026-11-09; future commits require their own validation.

## Capability matrix

| Capability | Status | Evidence / gap |
|---|---|---|
| Console visual prototype | Prototype | React, synthetic examples only |
| Alert ingestion + idempotent inbox/outbox | Prototype | PG models/API; live integration and delivery contract unqualified |
| Log query | Feature-flagged prototype | Query DSL tenant filter; no verified OpenSearch DLS/production index mappings |
| Metrics and traces end-to-end | Not integrated | Metrics endpoint intentionally returns 501 |
| Correlation/deduplication | Read-only preview | Exact source IDs, symptom/service/CI/time; no durable incident clustering |
| CMDB impact | Unverified estimate | No live Twin/GLPI authority validation |
| Canonical Core/Temporal | Existing in `aiops`, not connected | Read-only authenticated adapters pending |
| ITSM ticket sync | Not integrated | GLPI ownership remains in `aiops` |
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
