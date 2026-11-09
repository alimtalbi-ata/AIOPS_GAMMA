# AIOPS_GAMMA — executable roadmap

Tracking: GitHub Issues in this repository. Every workstream requires acceptance tests, an explicit upstream owner, and a reviewable PR. **No dates or owners are promised until assigned.**

| Stage | Outcome | Dependencies | Exit criteria |
|---|---|---|---|
| P0 — foundation | UI, backend, PG, docs, CI | none | Tests green, synthetic content clearly marked, docs and handover present |
| P1 — trusted reads | Core/Evidence/Twin/GLPI read-only integrations | authenticated tenant gateway, upstream API contracts | Positive/negative tenant tests, timeout/redirect/oversize rejection, no LIVE write |
| P2 — telemetry + LLM KPI | OTel → Data Prepper → OpenSearch, Cortex queries; Sentinel/ArgusLM read-only telemetry, qualified KPI history and SLOs | real index mappings, TLS, DLS/RBAC, source API contracts and model/tenant ACLs | Verified logs/traces/metrics and timestamped LLM KPI with source provenance, sample coverage and tenant scoping |
| P3 — incident operations | persistent dedup/correlation, CMDB impact, ITSM sync | P1+P2, canonical Core ownership | Replay, concurrency, idempotent ticket creation, reconciliation and stale-CMDB tests |
| P4 — AI investigation | RCA Analyst/Critic, evidence provenance, recurrence | P3, bounded read-only tool gateway | Benchmark on injected failures; cited supporting/contradictory evidence, UNKNOWN allowed |
| P5 — safe planning | approved runbooks, risk model, policy/HITL, dry-run | P4, approved procedure catalog | No unapproved recipe, replayed receipt or unauthorized actor can pass |
| P6 — qualified autonomy | audited execution and recovery verification | P5, Temporal/Worker, rollback qualification | Failure injection, idempotency/fencing, rollback, post-action SLI and ITSM closure verified |

## Priority and work intake
- **P0 urgent:** tenant ACL and safe adapter boundaries; CI/migrations and documentation.
- **P1 next:** observability mappings and correlation/ITSM reliability.
- **P2 research:** RCA benchmark, policy safety, postmortems.
- One GitHub Issue per independently testable deliverable; link code PRs and attach CI.
- Issue states: open = backlog/in progress; closed = acceptance evidence attached. Labels may refine this when configured.
- Review weekly or at each milestone; this document does not create an automatic schedule.

## External SRE reference review (research input)

Two curated research directories now inform implementation criteria: [awesome-sre-skills](https://github.com/alimtalbi-ata/awesome-sre-skills) and [awesome-devops-ai](https://github.com/alimtalbi-ata/awesome-devops-ai). See [SRE-REFERENTIALS](SRE-REFERENTIALS.md) for priority, selection, qualification and exclusions. First candidates: typed OpenSearch/OTel read-only investigation, SLO/error budgets, incident/postmortem templates, K8s diagnostic shadow mode and sandbox/Policy controls. **None are installed or approved for LIVE.**

## ITIL 4 compatibility gates

- #2: tenant-verified CMDB CI identity, ITSM system-of-record and authenticated service access.
- #4: Incident management and Problem management: priority/impact matrix, SLA and KEDB references, idempotent ITSM incident/problem lifecycle.
- #5: supporting and disconfirming RCA evidence, problem and known error candidate, blameless postmortem.
- #6: Change enablement: standard vs normal vs emergency change authority and models, RFC proposal, risk/rollback/verification, independent policy and receipt validation.
- [ITIL 4 governance and contract](ITIL4-GOVERNANCE.md) is authoritative for the target workflow; no official certification claim.


## KPI workstream — staged delivery

| Milestone | Status | Acceptance evidence required |
| --- | --- | --- |
| K0 — define KPI vocabulary | **Delivered in draft PR #1** | [LLM-KPI-CONTRACT](LLM-KPI-CONTRACT.md): metric formulas, units, missing data, source mappings, cost estimate vs billing |
| K1 — non-authoritative KPI preview | **Delivered in draft PR #1** | Authenticated `POST /api/v1/observability/llm/kpis/preview`; tests for percentiles, tenant rejection, invalid/partial data; Python checks passed on `73ab1335` |
| K2 — Sentinel trusted metrics | **Not started** | Pinned Prometheus metric contract, tenant/model-scoped backend query, counter reset handling, real staging data, no browser-side raw scrape |
| K3 — ArgusLM trusted measurements | **Not started** | Read-only authenticated adapter, model/tenant authorization, uptime and benchmark schema tests, bounded payload and secret rotation |
| K4 — durable KPI history | **Not started** | UTC timestamps, source watermark, idempotent ingestion, retention, sample count, freshness/coverage, per-model and tenant query windows |
| K5 — SLO + dashboards | **Not started** | Enterprise-owned SLO/error budgets, alerts with low-sample safeguards, Grafana/console panels using qualified real data, staged evaluation |

**Dependency:** K2/K3 require independently verified upstream ACL and egress controls; K4 depends on K2/K3; K5 requires trustworthy history. No benchmark, alert or KPI excursion grants execution authority. GLPI staging qualification is a separate P1 gate.
