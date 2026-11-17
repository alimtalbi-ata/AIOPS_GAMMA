# AIOPS_GAMMA — AI SRE target architecture

Sources reviewed:
- alimtalbi-ata/aiops: `docs/ARCHITECTURE-AND-BOUNDARIES.md`, `docs/COMPONENT-CATALOG-AND-REUSE.md`, `app/core/main.py`, `app/policy/main.py`, `app/evidence/main.py`.
- alimtalbi-ata/observability-stack: OpenTelemetry Collector, Data Prepper, OpenSearch Dashboards, Cortex/Alertmanager.
- alimtalbi-ata/aurora: evidence-linked investigations, incident recurrence grouping, security/redaction.
No actual LIVE API/tenant authorization validation has been performed.

## Product goal

AIOPS_GAMMA is an **AI Site Reliability Engineer platform** for multi-source operations, not only an APM dashboard.

1. **Observe and anticipate** — collect OTel logs/traces/metrics, health, anomaly, error-budget and predictive signals; record freshness and sample quality.
2. **Normalize and correlate** — stable event IDs, tenant/source identity, event-time windows, deduplication, topological grouping, recurrence history; never confuse cross-tenant coincidences.
3. **Determine impact** — map service/CI relationships via CMDB/GLPI and Digital Twin; distinguish observed edges from inferred edges; quantify blast radius with uncertainty.
4. **Open and reconcile ITSM tickets** — synchronize incidents, severity, affected CIs, ownership, evidence and timeline through idempotent adapters; preserve ITSM authority.
5. **Investigate using evidence** — acquire metrics/logs/traces/deployments/change context, generate RCA hypotheses, invoke Analyst + Critic, cite exact source refs and times; UNKNOWN is legitimate.
6. **Recommend safe resolution** — match versioned enterprise-approved runbooks, scope target/assets, evaluate dry-run, expected impact and verified rollback.
7. **Enforce deterministic policy** — policy engine independent of LLM, qualified authenticated tenant/actor/asset identity; least privilege, risk scoring, freshness and fencing. P1/high risk block autonomous execution.
8. **Execute and verify** — only via canonical Core → Temporal/Worker and a bound, expiring, one-use authorized receipt; audit effects, verify SLI recovery, reconcile ticket/CMDB and rollback where qualified.
9. **Learn** — incident recurrence indexing, evidence-verified runbook improvement, postmortem and human feedback; never silently grant new action permissions.

## Ownership map: preserve prior `aiops` platform

| Authority | Existing service | Gamma integration |
|---|---|---|
| Incident / Run lifecycle | `aiops` Core | Ingest canonical events via versioned API; **no second authoritative writer** |
| Workflow and execution receipts | Temporal / Worker | Read-only state + explicit authorized command delegation |
| CMDB / GLPI / ITSM | Existing GLPI + core integration | CI mapping, ticket cross-reference, freshness |
| Evidence and provenance | Evidence Center | Reference canonical evidence IDs; Gamma PG evidence is integration cache |
| Service dependency and simulation | Twin / Simulator | Enrich service map with observed telemetry; keep simulator isolated |
| Remediation policy / HITL | Policy | Only authoritative gate; Gamma preview endpoint is advisory |
| Intelligence | Analyst/Critic/Copilot + optional Aurora/Holmes evaluation | Evidence-grounded hypothesis generation via restricted tools |
| Telemetry | OpenSearch Observability Stack + existing monitoring | OTel → Data Prepper → OpenSearch; metrics → Cortex; dashboards reuse |

## Proposed domain contracts

Canonical alert event: `event_id`, `tenant_id`, `source`, `external_event_id`, `observed_at`, `ingested_at`, `service/ci`, `severity`, `fingerprint`, `evidence_refs`, `confidence`, `schema_version`.

Canonical incident: `incident_id`, `tenant_id`, `run_id`, `source_event_refs`, `ci_refs`, `status`, `classification`, `symptoms`, `evidence_refs`, `itsm_ref`, `last_observed_at`, `owner`, `version`.

RCA finding: `hypothesis`, `supporting_evidence_refs`, `contradicting_evidence_refs`, `ruled_out`, `critic_verdict`, `confidence`, `unknowns`, `model/prompt_version`, `run_id`.

Remediation proposal: `incident/run_id`, `target_asset_id`, `approved_runbook_id/version`, `input_params_hash`, `precondition_refs`, `risk_grade`, `reversal_plan_ref`, `policy_version`, `decision`, `HITL_receipt_ref`, `idempotency_key`, `verification_plan`.

## Deterministic autonomy levels

- **L0 Observe:** always read-only.
- **L1 Triage:** normalize, correlate, assess and propose; no writes beyond operational bookkeeping.
- **L2 Investigate:** bounded, authenticated read-only tool calls; human-visible evidence.
- **L3 Propose:** produce a runbook-backed plan, simulation, risk analysis and ITSM draft.
- **L4 Execute (future, explicitly qualified):** only approved, low-risk recipes on owned assets with verified preconditions, authenticated one-time approval or formally reviewed autonomous authorization policy, idempotency, fencing, audit and outcome verification. **Not implemented or authorized** in this repository.

## Release stages and verification gates

1. P0: Basic React console + backend schema, unit tests and CI.
2. P1: Read-only authenticated adapters to Core/Evidence/Twin and ticket references, with tenant boundaries.
3. P2: OTel/Data Prepper metrics and trace ingestion; OpenSearch index isolation and saved APM views.
4. P3: Dedup/correlation engine, incident groups, history and CMDB/ITSM reconciliation.
5. P4: Analyst/Critic RCA shadow-mode, citation checks and cross-incident learning.
6. P5: Approved runbook catalog, dry-run and deterministic policy/HITL gate.
7. P6: Instrumented, controlled execution with verified rollback, reconciliation and audit. No uncontrolled AI shell executor.

## Acceptance criteria

- No cross-tenant data exposure; no secret in browser or LLM context.
- No automated LIVE mutation without independently verified binding and authorization.
- Idempotent alerts, Core commands and ITSM ticket creation.
- Incident source, affected assets, topology confidence and evidence provenance are inspectable.
- No fabricated RCA findings; disconfirming evidence and UNKNOWN preserved.
- OpenSearch failure must not disable existing incident lifecycle.
- Replay, retry, duplicate, stale CMDB and rollback scenarios validated.
- Product dashboards distinguish live telemetry from synthetic demonstration data.

**Current state:** Gamma implements a prototype UI, PostgreSQL integration tables, optional telemetry adapter, reusable pure functions, and a **non-authorizing** policy preview. None of these statements imply LIVE operations qualification or autonomous remediation.
