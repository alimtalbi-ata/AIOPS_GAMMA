# GAMMA RC evidence freeze — UX15.42.1
Date: 2026-11-18. Decision: CI PASS; RC CONDITIONAL; HOLD / NO_GO LIVE.
Candidate: [PR #12](https://github.com/alimtalbi-ata/AIOPS_GAMMA/pull/12), exact SHA `59f3627e379084a3dd1a4c25d9f61065b0b87531`. Foundation source a1a1641829340d84c6329932975b355f8d298f72 (selected protections, not a full branch merge).
Review branch: review/gamma-rc-evidence-59f3627. This document is not a new qualified executable SHA or approval.

## Evidence index
All four runs were rechecked against the exact candidate SHA; all 13 jobs returned success.
| Workflow | Run | Jobs (name: ID) |
|---|---|---|
| Python | [44373935789](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44373935789) | intelligence-preview:135047891730; gateway-replay-postgres:135047892174; frontend:135047892187; test:135047892192; tenant-evidence-postgres-e2e:135047892196 |
| Deployment | [44373935854](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44373935854) | postgres-nonroot-experiment:135047892071; ui-image:135047892540; single-directory-runtime:135047892572; helm:135047892631; compose:135047892636; api-postgres-runtime:135047892664 |
| RLS | [44373936005](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44373936005) | qualify:135047892657 |
| Preflight | [44373935874](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44373935874) | role-preflight:135047892214 |

Prior log review: Python 2481 passed, 15 skipped, 12 warnings, 8 subtests passed; replay 19 passed; evidence E2E 15 passed; RLS 60 passed; simulated rootless 23 passed. Counts overlap; do not sum. The main Python invocation excludes three dedicated PostgreSQL test files and does not use -rs. No Python run artifacts were listed in the prior audit. Links index remote evidence, not an immutable archive of logs.

## Security matrix
| Control | Evidence | Boundary |
|---|---|---|
| Restricted application role, schema audit, negative drift | Preflight | not comprehensive production permissions attestation |
| Migration 0006, round trip, RLS, worker separation | RLS | disposable PostgreSQL |
| HMAC, replay, tenant ACL | Python/replay/E2E | not trusted gateway owner approval |
| Multi-key registry | Helm/Compose | no real key rotation |
| Rootless one-shot controls | Compose | simulated audit; real target unqualified |
| Restore | single-directory-runtime | table-scoped smoke only |
| Frontend and preview | frontend/ui-image/intelligence-preview | browser accessibility and external provenance unqualified |
| Outbox | Python/RLS | relay remains disabled; no LIVE |
| Canonical service access | issue #2 | open; no LIVE |

## Open reservations and closure criteria
| ID | Priority | Owner proposed | Closure evidence |
|---|---|---|---|
| RC-01 | P1 | QA | enumerate 15 skips with node IDs/reasons, review 12 warnings, map dedicated coverage |
| RC-02 | P0 | Release manager | map Git conflicts (prior state dirty); reviewed reconciliation on separately authorized branch and fresh full CI |
| RC-03 | P0 | Canonical owners | issue #2 actor/tenant/resource ACL, readonly contracts, negative SSRF/schema/availability tests |
| RC-04 | P0 | Gateway/IdP owners | signed identity/network/mTLS/header stripping and key custody evidence |
| RC-05 | P1 | Foundation | target rootless host UID/mount and task audit evidence |
| RC-06 | P1 | Gateway owner | approved nonproduction rotation and rollback exercise; never restore compromised keys |
| RC-07 | P1 | Operations | full backup/restore exercise and recovery evidence |
| RC-08 | P1 | UX | browser keyboard, focus, contrast, responsive, synthetic labels and network audit |
| RC-09 | P2 | Documentation | refresh historical convergence/runbook references without rewriting history |
| RC-10 | P0 | Release manager/security | explicit owner approvals and separate production authorization |

Skip conditions identified in source include disposable DB opt-in, restricted gamma_app and explicit OpenSearch staging activation. Exact 15-case mapping remains unverified.

## Inter-agent handover
Foundation: review PG16 role/schema/worker protections and deployment evidence.
UX: review HTTP isolation, ACL, offline console and browser qualification.
Gateway/IdP: review trust boundary, replay and key rotation runbook.
Canonical owners: review [issue #2](https://github.com/alimtalbi-ata/AIOPS_GAMMA/issues/2) and readonly contracts.
Security reviewer: review exclusions, threat model and negative evidence.
Release manager: maintain freeze, conflict assessment and acceptance board.
All six proposed signoffs: PENDING. No contact or approval is claimed.

Reference: docs/FOUNDATION-UX-CONVERGENCE.md and docs/GATEWAY-ROTATION-OPERATIONS.md at candidate SHA. Historical statements in those files may predate integrated results.
No merge, rebase, deployment, production data access, real key changes or automated remediation authorized. Any changed executable candidate requires qualification on its own exact SHA. Documentation branch CI, if triggered, does not replace candidate CI.
