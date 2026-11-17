# Gamma UI — UX1 dark console implementation

Date: 2026-11-17

## Scope delivered

- Added a dark-first visual theme to the existing React/Vite console.
- Expanded Overview into a Command Center with a source-provenance strip, priority incident queue and service-impact snapshot. All entries are explicitly marked as preview/offline or synthetic.
- Added a Signal Explorer workspace with Logs, Metrics and Traces tabs, local filtering, trace inspection, and an explicit synthetic-data disclaimer.
- Expanded Incident Workbench with competing unconfirmed hypotheses, a fixture-derived dependency blast-radius list, evidence timeline and source citations.
- Added an AI Intelligence Center UI with analyst hypotheses, critic guardrail checks, evidence coverage and an explicit deterministic local-simulation result. No model or remote API is invoked.
- Added a backend integration-readiness panel documenting the existing investigation and LLM KPI preview endpoints, their limitations, and the gateway/tenant-ACL blocker. No browser-to-API calls were added.
- Restyled the navigation shell, header, cards, tables, status tags, service map, incident groups, evidence panels and trace/incident drawers.
- Preserved the existing five page flows and their current React state/interaction logic.
- Clarified the header demo marker to **DÉMO · DONNÉES SYNTHÉTIQUES**.

## Safety and data semantics

This is a presentation-only increment. It does not add API calls, live polling, credentials, tenant selection, ITSM writes, or remediation controls. Existing bundled fixtures remain synthetic. The dark theme must not be interpreted as a live integration or production readiness.

## Verification status

- Source changes committed on `feat/gamma-ui-ux1-dark-console`.
- A frontend build, browser visual review, accessibility review, and exact-HEAD CI have **not** been run in this environment.
- The repository's existing CI runner/qualification blocker remains independent and unresolved.
- Do not merge or deploy based on this UX-only change without a successful frontend build and review.

## Next UX increments

1. Qualify source contracts, tenant authorization and provenance before replacing Signal Explorer fixtures with real logs, metrics and traces.
2. Replace fixture-derived blast radius and timeline with tenant-authorized, timestamped source records only after provenance and API contracts are qualified.
3. Obtain gateway/IdP owner approval, server-side proxy design, tenant/resource ACL evidence and exact-HEAD CI before any API connection.
4. Connect Sentinel / ArgusLM only through documented server-side read-only connectors, source provenance, audit logging, model evaluation and human approval gates. Existing preview endpoints accept caller-supplied data and are not live connectors.


## UX6 — Sentinel / ArgusLM connector qualification (2026-11-17)

### Findings from source inspection

- Sentinel repository: `alimtalbi-ata/sentinel-llm`, branch `main`.
  - `crates/sentinel-api/src/routes.rs` exposes `GET /metrics`, query routes and agent routes including `POST /api/v1/agents/anomaly/detect`.
  - Agent POST routes use execution-context middleware and require `X-Parent-Span-Id`.
  - `crates/sentinel-api/src/handlers/metrics.rs` exports Prometheus text; the inspected route contract does not establish tenant-scoped metric authorization.
  - `crates/sentinel-api/src/handlers/anomaly.rs` currently returns a placeholder `anomaly_detected=false`; do not represent this endpoint as production anomaly detection without further implementation evidence.
- ArgusLM repository: `alimtalbi-ata/arguslm-llm`, branch `master`.
  - `arguslm/server/api/monitoring.py` exposes monitoring config, run and uptime-history endpoints.
  - The inspected uptime query has no tenant predicate and the monitoring router handlers do not declare an authentication dependency. It is not safe to proxy into a multi-tenant Gamma workspace as-is.
- Gamma backend:
  - `POST /api/v1/incidents/investigation/preview` evaluates caller-supplied references and hypotheses; it does not authenticate source content or establish causality.
  - `POST /api/v1/observability/llm/kpis/preview` aggregates caller-supplied observations; it is not a Sentinel/ArgusLM connector.
  - `app/reused/upstream.py` deliberately fails closed pending independent actor/tenant/resource ACL qualification.

### UX6 implementation decision

The AI Intelligence Center now distinguishes Gamma preview APIs from Sentinel and ArgusLM upstream APIs and displays explicit NOT TENANT-QUALIFIED states. No network connector, credentials, browser request, polling or data ingestion was added. This is intentional: wiring these endpoints directly would risk cross-tenant disclosure or misrepresent placeholder telemetry as trusted intelligence.

### Required upstream gates

1. Sentinel owner: document authentication, tenant/resource scoping, metric naming, counter semantics, retention, timestamps and production implementation status for each agent route.
2. ArgusLM owner: add authenticated tenant/model-scoped read-only monitoring endpoints; ensure every query includes server-derived tenant scope and resource ACL.
3. Gateway owner: approve actor→tenant→resource identity, secret delivery/rotation, replay policy and network path.
4. Gamma: implement fixed-origin server-side connectors only after the above contracts are approved; persist provenance (tenant, source, resource, observed_at, fetched_at, window, coverage, source version) and reject stale/ambiguous records.
5. Qualification: exact-HEAD CI, cross-tenant negative tests, source outage/timeout tests, data minimization, audit trail and human-reviewed RCA benchmark.

**Decision: NO CONNECTOR ACTIVATED.** No production data has been fetched and no upstream integration is qualified.
