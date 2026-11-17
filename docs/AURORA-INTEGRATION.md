# Aurora analysis and controlled reuse — Gamma

Source: https://github.com/alimtalbi-ata/aurora (upstream Arvo-AI/aurora).
Source tree inspected on main (commit/tree `98f15ffe984838bc03c12f2a9b4495894ce88435`).
Aurora is Apache-2.0, copyright Arvo A.I. Ltd.; this integration uses independently authored adaptations with attribution, **not** a vendored Aurora deployment.

## Selected capabilities

- **Incident recurrence folding** — Gamma's `frontend/src/data.ts` uses the anchor/occurrence approach from Aurora `client/src/lib/incident-grouping.ts`. Orphans stay visible; fold only when an anchor exists. Data are synthetic fixtures, not real incident correlation.
- **Evidence-first RCA** — investigation detail shows explicitly linked evidence identifiers and unverified hypotheses. Inspired by Aurora `server/chat/backend/agent/prompt/rca_sections/evidence_standard.md` and `CitationBadge.tsx`.
- **Credential redaction** — Gamma `app/reused/redaction.py` adapts Aurora's `server/utils/auth/log_redact.py` token/JWT patterns and fails closed on very long content. Applied to stored evidence summaries and relay error diagnostics; it is **not** a complete DLP engine.
- **Incident information layout** — lightweight drilldown/expansion inspired by Aurora incident and correlated-alert panels, implemented as original Gamma React markup rather than copying Next.js components.

## Deliberately not imported

- Aurora Flask, Celery, Redis, Vault, Memgraph, LangGraph: this would duplicate Gamma's existing FastAPI/PG/CMDB/RCA services.
- Autonomous command execution, cloud credentials, Kubernetes executor and remediation: no independently qualified tenant authorization, sandbox and HITL contract.
- Aurora's full Next.js UI: too tightly coupled to Aurora's API/security models.
- Third-party brand logos, proprietary data and deployment credentials.

## Observability UI reuse

`alimtalbi-ata/observability-stack` already ships OpenSearch Dashboards (APM service map, traces, Explore, Alert Manager), OTel Collector, Data Prepper and Cortex. Gamma uses a distinct portal for incidents/RCA and a safe external link to dashboards. Avoid copying its dashboards frontend or enabling CORS-bypassing iframe access.

## Security/operational boundary

The Gamma frontend is **demonstration-only**, served separately from the privileged API, with static synthetic metrics and clearly labeled data. Never place `INTERNAL_API_KEY` or tenant credentials in client-side code. Integrate authenticated backend read-models after OIDC/mTLS tenant enforcement and multi-tenant tests. OpenSearch dashboards needs its own authentication and role rules.

## Roadmap

1. CI and build verification of the frontend with node/toolchain.
2. Backend read-models served behind authenticated BFF (replace demo fixtures).
3. Official Data Prepper/OTel stack pin, security policies and topology reconciliation.
4. Evidence/RCA shadow-mode tests, feedback, recurrence matching with real immutable incident IDs.
5. Authorized actions only via Policy/HITL workflow.
