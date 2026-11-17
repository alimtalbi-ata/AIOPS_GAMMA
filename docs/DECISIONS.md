# Architecture decision log

Decisions are append-only; supersede with a new numbered ADR rather than rewriting history.

## ADR-001 — Keep existing AIOps Core authoritative (2026-11-09)
**Decision:** Gamma is an experience/integration layer. Existing `aiops` Core owns incidents and Runs; Evidence Center owns canonical evidence; Temporal/Worker owns workflow; Policy/HITL owns remediation authorization. **Reason:** prevent split-brain incidents, duplicate ITSM tickets and policy bypass. **Consequence:** read-only adapters and idempotent delegated commands must be qualified.

## ADR-002 — Reuse upstream telemetry stack (2026-11-09)
**Decision:** use OpenTelemetry/Data Prepper/OpenSearch for logs/traces and Cortex/Prometheus for metrics; do not create a competing metric store. **Reason:** source `observability-stack` already supplies those components. **Consequence:** index schema and tenant isolation must be validated against real deployment.

## ADR-003 — Adapt Aurora investigation patterns, not its entire control plane (2026-11-09)
**Decision:** borrow evidence-linked RCA, recurring incident UX, bounded read-only tools and postmortem patterns. **Reason:** Aurora's Flask/Celery/LangGraph stack overlaps Gamma and Core. **Consequence:** integrations must have stable contracts and respect third-party licensing.

## ADR-004 — Deny LIVE execution by default (2026-11-09)
**Decision:** Gamma policy and correlation previews never authorize LIVE actions. **Reason:** model confidence, synthetic identities and boolean approval flags are insufficient. **Consequence:** future execution requires independently verified tenant/actor/asset authorization, approved runbook, preconditions, signed one-use receipt, fencing, audit and rollback.

## ADR-005 — GitHub as handover system of record (2026-11-09)
**Decision:** GitHub Issues track work; PRs hold evidence; ROADMAP tracks gates; HANDOVER and PROJECT-STATUS preserve restart context. **Reason:** continuity across contributors and assistant sessions. **Consequence:** docs must be refreshed at each meaningful delivery.
