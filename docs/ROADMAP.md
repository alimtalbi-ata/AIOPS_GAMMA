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

## Product use-case traceability

The [UC01–UC10 catalog](USE-CASE-CATALOG.md) maps operator journeys to current endpoints, maturity, release dependencies and acceptance gates. Use it when prioritizing work so implementation remains tied to platform use cases rather than isolated technical hardening.

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

## UX design track (inspiration from production AIOps patterns)

[PRODUCT-UX-DESIGN](PRODUCT-UX-DESIGN.md) maps Command Center → Signal Explorer → Incident Workbench → RCA Evidence → LLM KPI → Runbook/Change → Audit/Learning. UX0–UX5 are proposed increments, not shipped screens. Prioritize UX0/UX1 (clear demo/provenance states and KPI preview) before adding live-looking graphs. Never treat a UX approval as authorization for ITSM writes or LIVE remediation.

## AI SRE investigation evaluation track

The fifth design reference, [AI SRE complete guide (2026)](https://dev.to/siddharth_singh_409bd5267/ai-sre-the-complete-guide-for-engineering-teams-in-2026-51ba), informs the [UX blueprint](PRODUCT-UX-DESIGN.md) without qualifying vendor claims. Before autonomous remediation, prioritize: (1) an allowlisted read-only multi-step investigation loop; (2) source-cited hypothesis/contradiction and UNKNOWN handling; (3) human-adjudicated RCA accuracy and time-to-RCA benchmarking; (4) reviewable postmortem drafts; (5) bounded tool/model cost and security audits. **None of these new AI SRE effectiveness KPIs are implemented by the existing Sentinel/ArgusLM model-performance preview.** Start with one service and one alert source in shadow mode. L4 execution remains a separate Policy/HITL release gate.

## Architecture and reuse delivery gates

The target [AI SRE architecture](TARGET-ARCHITECTURE-2026.md) and [GitHub reuse inventory](REUSE-COMPONENT-INVENTORY.md) prioritize canonical `aiops` Core/Policy/Evidence/GLPI and `observability-stack` as P0 integration boundaries, then Sentinel/ArgusLM read-only KPI sources and one qualified investigation engine. Implementation gates: P0 ownership/license review; P1 OIDC/tenant contracts; P2 telemetry/KPI connectors; P3 correlation/GLPI staging; P4 shadow investigation; P5 verified KPI/SLO UX; P6 separately approved execution. Do not treat architecture docs as completed integration.

## Mandatory deployment parity gate

All GAMMA-operated components must ship as versioned OCI images with **both Docker Compose and Kubernetes/Helm** deployment paths. Compose supports local/demo/integration; Kubernetes supports staging/production. Require CI Compose smoke tests, Helm lint/template/schema/policy checks, staging multi-tenant tests, observability, secrets, persistent backup and rollback before promotion. Externally managed GLPI/SSO/SaaS endpoints remain external dependencies; their GAMMA connectors must deploy in both environments. See [DEPLOYMENT-CONTRACT](DEPLOYMENT-CONTRACT.md). This is a new required gate, **not a claim that all packaging is implemented**.

## Mandatory rootless single-directory qualification

Every self-hosted GAMMA component must support a configurable `GAMMA_HOME` directory for application artifacts and persistent data, no writes to host system directories, rootless Docker/Podman operation in Compose, and non-root restricted workloads in Kubernetes. Per-component UID/permissions, persistent mounts, rootless daemon data-root, upstream images, K8s CSI/runtime exceptions and backup/restore must be qualified before release. See [ROOTLESS-SINGLE-DIRECTORY](ROOTLESS-SINGLE-DIRECTORY.md). The current overlay is opt-in and **not yet production qualified**.


## Use cases and acceptance gates (2026-11-14)

These scenarios are product requirements, not claims of production readiness.

| Use case | User outcome | Essential negative tests | Gate |
|---|---|---|---|
| UC01 Command center | Tenant-aware signals with source, freshness and DEMO/REAL marking | Unauthorized, cross-tenant, missing or stale data | P0/P1 |
| UC02 Alert correlation | Deduplicated incidents by source ID, time, service and CI | Retries, concurrent duplicates, cross-tenant collision | P2/P3 |
| UC03 Investigation | Linked logs, metrics, traces, changes and cited evidence | Timeout, oversize, missing/contradictory evidence, SSRF | P2/P4 |
| UC04 Impact | Conservative CMDB/Twin blast-radius estimate | Stale topology, unauthorized CI, unverified edges | P1/P3 |
| UC05 ITSM/GLPI | Incident priority and ticket preview, later idempotent reconciliation | Cross-entity access, duplicate ticket, conflict, no preview writes | P1/P3 |
| UC06 AI RCA | Analyst/Critic hypotheses, contradictory evidence, UNKNOWN and review | Cross-tenant leakage, prompt injection, invented references | P4 |
| UC07 AI/LLM SLO | Latency, TTFT, throughput, errors, sample coverage and cost estimates | Bad provenance, missing samples, counter reset, model ACL | P2 KPI |
| UC08 Runbook/Change | Versioned dry-run, risk, rollback and ITIL approval proposal | Unapproved runbook, stale evidence, unauthorized actor | P5 |
| UC09 Controlled recovery | Future Core/Temporal execution and post-action SLI verification | Replayed/expired receipt, race, partial failure, rollback | P6 only |
| UC10 Postmortem | Cited timeline, recurrence and reviewed lessons | Redaction, uncertainty, tenant isolation, human approval | P4/P6 |

**First synthetic acceptance scenario:** ingest duplicate alerts for one service; present a single correlated preview with source IDs and evidence freshness; estimate conservative CMDB impact; propose an ITSM incident without a Core/GLPI write. Assert that an unrelated tenant cannot observe the scenario, that missing evidence remains UNKNOWN, and that all UI data are identified as synthetic. This scenario is **not yet executed**.

**Release boundary:** exact-HEAD CI and real disposable PostgreSQL, gateway actor→tenant→resource ACL, upstream contract and deployment parity tests remain mandatory. Draft / HOLD / NO_GO. No merge, LIVE reads or remediation, production PostgreSQL access, or deployment.
