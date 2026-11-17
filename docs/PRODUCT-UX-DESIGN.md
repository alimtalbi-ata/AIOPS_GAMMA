# AIOPS_GAMMA — product UX blueprint: evidence-first AI SRE

**Status:** proposed UX specification, not a claim that the screens or integrations are already shipped. Applies to the React demo in draft PR #1; production use requires source-qualified telemetry and authenticated RBAC.

## Design references (inspiration, not deployment authority)

1. [Four LLM Workflows That Actually Survive Production](https://dev.to/nimay_04/four-llm-workflows-that-actually-survive-production-48h9) — structured extraction, deterministic facts, confidence-based triage, human fallback, adversarial evaluation.
2. [AIOps That Actually Helps: Start with Telemetry, Correlation, and Safe Automation](https://dev.to/nimay_04/aiops-that-actually-helps-start-with-telemetry-correlation-and-safe-automation-4p1j) — observability before agents, incident-centric noise reduction, linked logs/traces/metrics/deployments, safe action gates.
3. [RAG Is Not Always the Answer Anymore: How AI Agents Search Code in 2026](https://dev.to/nimay_04/rag-is-not-always-the-answer-anymore-how-ai-agents-search-code-in-2026-43m3) — exact file/symbol/error searches, follow references, inspect tests, retain path/line evidence; semantic RAG remains optional for unstructured runbooks/docs.
4. [AIOps: Automating Incident Management with AI & Machine Learning](https://dev.to/yash_sonawane25/aiops-automating-incident-management-with-ai-machine-learning-4ebg) — collection, enrichment, anomaly detection, correlation, impact, incident handling, automation as a later qualified phase. The article's example of executing a restart script must **not** be copied into Gamma without Policy/HITL, runbook allowlisting and independent authorization.

These are conceptual references; product claims require Gamma-specific testing and actual source telemetry.

## Information architecture and primary navigation

| Area | Operator question | Primary UI |
| --- | --- | --- |
| Command Center | What is affecting customers now? | SLO health, active correlated incidents, impacted services, change markers, telemetry freshness |
| Signal Explorer | Which signals are real and related? | Filtered logs/metrics/traces/events, anomaly timeline, source and sample quality |
| Incident Workbench | What is the incident, owner and impact? | Correlated event cluster, canonical incident ID, affected CI/service map, ITSM status, owner and timeline |
| RCA Evidence | Why do we think this is the cause? | Hypothesis ranking, supporting and contradictory evidence, trace/file citations, UNKNOWN and critic verdict |
| LLM Performance | Are models meeting objectives? | Sentinel/ArgusLM KPI cards, P50/P95/P99, TTFT, TPS, error %, cost estimate, coverage and sample count |
| Runbook & Change | What would be safe to do? | Proposed approved runbook, dry-run, blast radius, rollback, ITIL change model, Policy/HITL status |
| Audit & Learning | What changed and did it work? | Human decisions, immutable source refs, verification, recurrence, postmortem, evaluation metrics |

The current React demo has Overview, Services, Application Map, Traces and Incidents & RCA; the rest are **target** views. Never label a target screen as live.

## Command Center — desktop composition

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ GAMMA / Workspace  Tenant [verified]  Env [prod/stage]  Time window  LIVE? │
├──────────────┬─────────────────────────────────────────────────────────────┤
│ Command      │ SLO health   Active incidents   Alert noise   Data freshness│
│ Signals      ├─────────────────────────────────────────────────────────────┤
│ Incidents    │ Service impact map            │ Incident priority queue     │
│ RCA Evidence ├───────────────────────────────┼─────────────────────────────┤
│ LLM KPI      │ Correlated signal timeline    │ Changes / deployment marks  │
│ Runbooks     ├───────────────────────────────┴─────────────────────────────┤
│ Audit        │ Source health + missing evidence + qualification banners   │
└──────────────┴─────────────────────────────────────────────────────────────┘
```

- Top bar: independently verified tenant, environment, source freshness and immutable time window; **not** browser-controlled tenant headers.
- Global badges: `DEMO / SYNTHETIC`, `PREVIEW / CALLER SUPPLIED`, `LIVE / SOURCE QUALIFIED`, `STALE`, `UNKNOWN` are mutually distinguishable and must never be silently converted into green/healthy.
- Main content should prioritize customer impact and incident clusters over raw alert counts. A reduction percentage is only displayed when measured against an explicit baseline and time window.
- Every number must expose source, sample count, time range, freshness, unit, coverage and click-through evidence. If unavailable show an em dash / `Données indisponibles`, **not** zero.
- Use a restrained light/dark compatible palette, high-contrast severity/status text, keyboard navigation and responsive stacked layout. Color must not be the only severity indicator.

## Incident Workbench — operator flow

`Detect → Deduplicate → Correlate → Impact → ITSM → Investigate → Propose → Approve → Verify`

1. **Cluster header:** canonical incident ID (or `PREVIEW`), affected service, severity from enterprise-owned matrix, event window, cluster confidence and incident owner.
2. **Evidence timeline:** each event/trace/log/metric/deploy/CI is linked by source ID, timestamp and tenant; inferred relationships are visually marked as hypotheses.
3. **Blast radius:** topology graph distinguishes observed, CMDB-confirmed and inferred edges; stale CI relationships are flagged.
4. **ITSM panel:** read-only GLPI snapshot when qualified; incident sync preview clearly states `NOT SUBMITTED`. Do not expose raw GLPI vendor payload.
5. **RCA panel:** show top hypotheses with supporting and contradicting evidence, critic outcome, missing data and `UNKNOWN`; no ungrounded confidence percentages.
6. **Runbook panel:** recommendation only, with scope, risk, dry-run and rollback. Execute button absent/disabled until independent Policy/HITL and backend enforcement are production-qualified.
7. **After action:** verify symptom SLI, track audit receipt and ticket reconciliation; this is future work, not existing behavior.

## LLM KPI workspace — Sentinel and ArgusLM

The initial source contract is [LLM-KPI-CONTRACT](LLM-KPI-CONTRACT.md); current API `POST /api/v1/observability/llm/kpis/preview` uses **caller-supplied** samples and is not a live data feed.

Recommended view:
- Filter bar: authorized tenant, environment, model/provider, service, version, time range and source status.
- First row: success %, error %, latency P95 (ms), TTFT P95 (ms), mean TPS, estimated cost USD. No misleading traffic-light grading without qualified SLO thresholds.
- Second row: P50/P95/P99 latency and TTFT trend, token usage and cost estimate trend, Sentinel anomaly events and correlated incident overlays.
- Data quality strip: sample count, partial token/cost coverage, source watermark, gaps, counter resets and small-sample warning.
- Detail drawer: definition/formula, aggregation window, metric provenance, version of price table, source link and missing data behavior.
- KPI-to-incident navigation: click an anomaly interval to open the correlated evidence timeline; **do not** automatically trigger remediation.

## Evidence-first investigation and code search

Tool strategy:
1. Retrieve tenant-scoped logs/traces/metrics, deployment markers, runbooks and incident context from allowlisted read-only adapters.
2. For code-specific hypotheses, prefer exact paths, symbols, stack trace strings, grep/ripgrep, dependency references and tests from a **separately authorized, read-only** repository connector. Cite commit SHA + file path + line range.
3. Use semantic search/RAG for long prose documents, KB and runbooks when needed; cite document version and passage. Never assume vector similarity proves causality.
4. Model returns typed hypotheses with `supporting_evidence_refs`, `contradicting_evidence_refs`, `unknowns` and `critic_verdict`; deterministic validation rejects fabricated references.
5. Display no evidence as `UNKNOWN` and provide a manual triage route. No arbitrary shell, credential retrieval, prompt injection execution or unapproved source indexing.

## Visual component inventory

- `KpiCard`: value + unit + time window + source + sample count + status, `null` as unavailable.
- `SourceStatusBar`: verified origin, freshness, schema/version, access scope.
- `IncidentClusterCard`: symptom, service/CI, grouped alert count, dedup rationale, priority and impact.
- `EvidenceTimeline`: filterable events with source IDs and timestamp; supports contradictory evidence.
- `TopologyImpactGraph`: typed edge provenance and freshness, no implicit causal claim.
- `HypothesisPanel`: evidence refs, critic and uncertainty; avoids unexplained confidence scores.
- `ITSMStatusCard`: GLPI read snapshot and advisory sync proposal, never implied mutation.
- `PolicyGate`: preview/blocked/approval-required/authorized, with action disabled unless backend attested.
- `CodeEvidenceLink`: repository, SHA, path, line range, tenant-scoped access.

## Prioritized implementation tickets and acceptance tests

| Phase | Deliverable | Acceptance |
| --- | --- | --- |
| UX0 | Add design vocabulary, explicit data provenance and status banners to existing demo | All demo numbers visibly synthetic, no false live indicators, keyboard and contrast review |
| UX1 | Add LLM KPI navigation and preview-only panel | Explicit sample count/coverage, missing values as unavailable, no live polling or invented figures |
| UX2 | Correlated incident workspace with evidence timeline | Every link carries source ref, tenant, event time; inferred links marked; empty/unknown states |
| UX3 | Read-only ITSM/CMDB and code evidence drawers | Authenticated tenant ACL and source-contract tests; no cross-tenant links, no writes |
| UX4 | Policy/HITL and qualified post-action verification | Separate backend authorization; safe rollback and audit receipts; no action button without enforcement |
| UX5 | Production-grade SLO/KPI dashboards | Trusted source connectors, timestamped facts, freshness/coverage, owner-reviewed SLOs and staging verification |

### Non-goals of this design iteration
No new live API calls, autonomous agent, code execution, production KPI feed, GLPI ticket write, or assertion that Sentinel/ArgusLM are deployed in Gamma.

## Fifth reference — autonomous read-only AI SRE investigation

Reference: [AI SRE: The Complete Guide for Engineering Teams in 2026](https://dev.to/siddharth_singh_409bd5267/ai-sre-the-complete-guide-for-engineering-teams-in-2026-51ba), Siddharth Singh, DEV (2026). This is a design input, **not** independent verification of the article's market statistics or vendor claims.

### What changes in Gamma's product experience

- **Investigation run as a first-class object:** an operator opens an incident and sees the investigation's current stage: alert intake → context gathering → hypotheses → evidence tests → RCA synthesis → optional recommendation → postmortem draft. Each stage has timestamps, source links, status, and an explicit stop/UNKNOWN outcome.
- **Read-only agent tool gateway:** an agent may select from allowlisted, tenant-authorized, bounded metric/log/trace/deployment/topology and repository-read tools. Every invocation displays tool name, scope, query template, elapsed time, result freshness and evidence reference. No arbitrary shell, kubectl write, credential exposure, or direct infrastructure mutation.
- **Hypothesis comparison:** show supporting evidence, contradictory observations, ruled-out hypotheses, missing evidence and human reviewer feedback. Correlation is not presented as proven causality.
- **Postmortem draft:** prefill impact, customer timeline, contributing factors, detection and response milestones, source citations, follow-up owners and action items. Label DRAFT until human review; never automatically close ITSM.
- **Autonomy ladder:** L0 observe, L1 triage, L2 investigate read-only, L3 propose runbook/PR under review, L4 execute only after independent enterprise Policy/HITL and backend safety gates. The current platform does **not** implement L4.
- **Provider independence:** record provider/model/version, token usage, estimated USD and evaluation metadata per investigation; permit approved provider selection without allowing models to bypass tool authorization.

### AI SRE quality and operational KPI scoreboard

| KPI | Definition | Qualification |
| --- | --- | --- |
| Time to first actionable hypothesis | hypothesis timestamp minus alert received timestamp | Source-qualified timestamps; show median/P95 and sample count |
| Time to evidence-backed RCA | reviewed RCA timestamp minus alert received timestamp | Distinguish AI draft from human-confirmed finding |
| RCA accuracy | human-adjudicated correct RCA / adjudicated investigations | Blinded review, explicit unknown/unresolved class, confidence intervals for small samples |
| Evidence citation validity | resolvable, tenant-authorized source refs / all claimed refs | Deterministic link and time-window validation |
| Alert noise reduction | (raw alerts - correlated incident groups) / raw alerts | Same tenant/window, track false merges and missed incidents |
| Investigation tool safety | rejected unsafe tool requests, cross-tenant denials, timeouts | Security events, not a performance success score |
| Human escalation rate | investigations escalated / eligible investigations | Track policy reasons and missing evidence; do not optimize to zero |
| Investigation cost | complete estimated model/tool cost per run | Label estimated vs billed, track coverage and model version |
| Postmortem completeness | required fields supported by valid evidence / required fields | Human-reviewed, no fabricated causal conclusions |

These **AI SRE process KPIs are proposed**, not implemented by the existing LLM request KPI preview API. The existing Sentinel/ArgusLM KPI contract measures model performance, not RCA correctness or MTTR.

### Read-only pilot acceptance plan

1. Select **one authorized service and one alert source** with an agreed evaluation window and baseline. Use historical replay and shadow mode first.
2. Run multi-step investigations with bounded time, tool-call and model-cost budgets; no writes. Require tenant ACL tests, timeout behavior and redaction.
3. Compare each RCA against independently adjudicated human outcomes; capture false positives, false merges, UNKNOWN, citations and operator effort.
4. Review the evidence quality and estimated costs before expanding service scope. Suggestions and PR drafts remain human reviewed; L4 requires a separate production qualification decision.

### UI acceptance additions

- Incident drawer gains an **Investigation Steps** timeline and explicit read-only tool receipts.
- RCA drawer gains side-by-side hypotheses with supporting/contradictory evidence and a human review state.
- KPI area separates **Model performance** (TTFT/TPS/cost) from **AI SRE effectiveness** (time-to-RCA, citation validity, adjudicated accuracy).
- Postmortem drawer exports a **reviewable draft** with immutable citations and an unresolved-questions section.
- An action control must never become enabled merely because an LLM claims high confidence.
