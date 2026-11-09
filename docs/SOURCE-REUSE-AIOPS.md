# Source reuse from alimtalbi-ata/aiops

Reviewed existing `aiops` architecture and source. This project must not replace or bypass authoritative Core/Temporal/Evidence/Policy.

## Candidate code: Policy

Source `app/policy/main.py` defines P1 escalation, missing-evidence UNKNOWN, synthetic SIMULATE and fail-closed LIVE effect checks. Gamma incorporates an **adapted** pure function `app/reused/policy.py`. It additionally requires runbook approval, low risk and verified asset owner before even considering read-only decisions. **No policy evaluator response grants LIVE execution.**

The existing Policy service remains canonical. A future adapter must authenticate to Core/Policy and obtain an independently validated policy response tied to run/tenant/CI/recipe/params and proof version, before any effect is attempted.

## Candidate code: Core

The `app/core/main.py` implementation demonstrates canonical `POST /api/incidents`, `POST /api/runs`, optimistic `POST /api/runs/{rid}/command`, gated evaluation and execution receipts. Gamma must not expose these directly to browsers or write Core's PostgreSQL tables. It should use an authenticated internal integration service and idempotency keys.

## Candidate code: Evidence

`app/evidence/main.py` exposes `GET/POST /api/evidence`, source and run-indexed queries, hash deduplication and evidence IDs. Gamma's existing local `investigation_evidence` is a cache/references table; the canonical Evidence service is the authority where configured. Source provenance should be immutable with freshness checks.

## Candidate code: Digital Twin / ITSM

The existing Twin model, GLPI integration and simulator are not to be duplicated in Gamma. Later qualification must check the runtime deployment topology, tenant authorization and exact service-to-service API contracts.

## Qualification caveat

All source review was static. Runtime endpoint availability, current deployed version, tenant-level ACL, worker isolation, real runbook allowlists and live approval receipts have **not** been tested. In particular, the prior platform Policy source explicitly says a boolean `human_approved` cannot authorize a LIVE effect.
