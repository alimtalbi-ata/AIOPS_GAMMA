# AIOPS_GAMMA — Handover / session recovery

**Snapshot: 2026-11-09.** Read this first when taking over work, after a session interruption, or when changing developer/agent.

## Current working state
- Repo: https://github.com/alimtalbi-ata/AIOPS_GAMMA
- Active draft PR: https://github.com/alimtalbi-ata/AIOPS_GAMMA/pull/1
- Branch: `feat/observability-foundation`; `main` does **not** contain the feature branch.
- Last verified pre-documentation commit: `8235693a1be7c28c49fa5ad8262f0d2209ccc49c`; its GitHub Actions checks passed. **Recheck HEAD and CI before changing or merging.**
- Working language: French for operator/product communication; code/docs may be English.
- Main docs: `docs/PROJECT-STATUS.md`, `docs/ROADMAP.md`, `docs/AI-SRE-PLATFORM.md`, `docs/THREE-SOURCE-INTEGRATION.md`, `docs/OPERATIONS.md`, `docs/DECISIONS.md`.

## Resume procedure
1. Read latest PR discussion, issues, branch HEAD, `git status`, CI and relevant docs.
2. Verify what actually exists in the three source repos; do not assume deployment/runtime availability from static source.
3. Select one GitHub issue and identify acceptance criteria, ownership boundaries and test strategy.
4. Make an incremental branch/PR update; avoid unreviewed copying of large upstream projects or credentials.
5. Run `pytest`, frontend build, migration and integration checks as applicable; inspect GitHub Actions on the **new HEAD**.
6. Update status, decisions and this handover with delivered code, SHA, tests, known failures, next issue and security qualifications.
7. Leave PR draft until reviewed and safe; do not auto-merge or enable LIVE remediation.

## Immediate priorities
1. Authenticated, tenant-qualified read-only Core/Evidence/Twin/GLPI adapters; strict fixed origins, no redirects, timeouts, bounded JSON, no secrets in frontend.
2. Real OpenTelemetry/Data Prepper/OpenSearch/Cortex contract and mapping tests.
3. Persistent correlation, deduplication and idempotent canonical Core/ITSM reconciliation.
4. Evidence-grounded RCA with critic, contradictory evidence and UNKNOWN outcomes.
5. Versioned approved runbooks, dry-run and deterministic policy/HITL; only then qualified effect execution.

## Known gaps and blockers
- Existing Core, Evidence, Policy, Twin and GLPI service endpoints/auth contracts not independently runtime-qualified.
- No production OIDC/mTLS or tenant-specific RBAC/DLS; shared internal key and X-Tenant-Id only safe behind a trusted gateway.
- Demo console uses synthetic data.
- Metrics API returns 501; OpenSearch query mapping must be checked against actual upstream pipeline.
- Policy preview is not an authorization token. LIVE mutation prohibited.
- Integration/e2e tests against deployed upstream systems not run.

## Handover note template (append in future updates)
```md
### YYYY-MM-DD — workstream / PR
- Branch / commit:
- Issue / PR:
- Delivered:
- Validation (exact commands, CI URL, pass/fail):
- Decisions and security impact:
- Not done / blockers:
- Next concrete action:
```

## First handover entry
### 2026-11-09 — three-source AI SRE foundation
- Branch / commit: `feat/observability-foundation` / `8235693a` (before documentation update)
- PR: #1 (draft)
- Delivered: FastAPI + React console, PostgreSQL inbox/outbox and evidence, feature-flagged OpenSearch log adapter, safe correlation preview, policy preview, source-reuse documentation.
- Validation: GitHub Actions checks for `8235693a` completed successfully.
- Security: no LIVE execution, no tenant authorization attestation, no production qualification.
- Next: implement tenant-qualified read-only Core/Evidence/Twin adapters.

### 2026-11-09 — SRE skills and AI DevOps reference selection
- Input catalogs: `alimtalbi-ata/awesome-sre-skills` and `alimtalbi-ata/awesome-devops-ai`.
- Delivered: `docs/SRE-REFERENTIALS.md`, curated candidates and source/safety qualification protocol; linked planned work to #2–#6.
- Security: directory links and skill instructions **are untrusted until audited**. No skills, MCP servers, code executors or credentials were installed/imported.
- Validation: documentation-only GitHub commit; check workflow status on new HEAD before merge.
- Next concrete action: implement tenant-qualified read-only Core/Evidence/Twin adapters (#2), then typed OTel/OpenSearch tool queries (#3).

### 2026-11-09 — initial fail-closed canonical read adapter (#2)
- Delivered: fixed-origin, HTTPS-only, GET-only, bounded JSON upstream snapshot prototype and negative tests; `docs/CANONICAL-READ-ADAPTER.md`.
- Status: disabled by default; paths and tenant attestation are provisional and **not qualified against live aiops services**.
- Next: validate upstream contracts, tenant-specific ACL/OIDC and network egress controls before activation; continue #2.

### 2026-11-09 — ITIL 4 enterprise interoperability contract
- Requirement: map AI SRE to incident management, problem management, change enablement and service configuration management; also event, service-level, knowledge and continual improvement practices.
- Delivered: `docs/ITIL4-GOVERNANCE.md`, typed ITSM/CI advisory projection at `POST /api/v1/itil4/workflow/preview` and tenant/cross-reference/policy-negative tests.
- Guardrails: ITSM owns incident/problem/change/CI identities, priority matrix and approvals; standard change type is **not** authorization; no LIVE execution.
- Next: qualify GLPI → ServiceNow/JSM plugin contracts by business tenant and enforce enterprise change models in independent Policy/HITL. Track in issues #2, #4, #6.

### 2026-11-09 — ITIL 4 enterprise incident sync preview (#4)
- Delivered: versioned enterprise priority matrix and deterministic side-effect-free ITSM incident proposal with stable idempotency key; `docs/ITSM-SYNC-CONTRACT.md`, `app/reused/itsm_contract.py` and tests.
- Security: caller-supplied priority matrix is **preview-only**; real policies must be server-resolved. No GLPI/ServiceNow/JSM calls, ticket creation or LIVE execution.
- Next: qualify tenant identity, ITSM contracts and durable canonical Core idempotency before any mutations. Check CI on new HEAD.

### 2026-11-09 — GLPI incident read-only prototype (#4)
- Branch / commit: `feat/observability-foundation` / `a001d1c9` (documentation commit; recheck HEAD).
- PR / issue: draft #1 / #4.
- Delivered: disabled-by-default GLPI ticket GET adapter, trusted single-tenant/entity binding, bounded TLS-only no-redirect HTTP, minimal response projection, API route, negative tenant/entity tests and `docs/GLPI-READ-ADAPTER.md`.
- Validation: tests added; GitHub Actions on latest HEAD still to be confirmed. No GLPI staging integration performed.
- Security: GLPI legacy API and service session token are provisional; no cross-tenant credential registry, no session lifecycle, no CMDB mapping or ITSM mutation.
- Next: version-pinned GLPI staging contract tests, ACL-backed tenant/entity registry, CI qualification and secret management before enabling the adapter.

### 2026-11-09 — GLPI CI recovery and API boundary tests (#4)
- Branch / last pre-handover commit: `feat/observability-foundation` / `aa661474`.
- PR / issue: draft #1 / #4.
- Delivered: incident-only GLPI ticket attestation (`type=1`), strict identifier/status validation, upstream decoding error handling, negative tests, and route-level auth/tenant denial tests.
- Validation: GitHub Actions Python checks **passed** for `b69374ac` (run 42674584843). Recheck CI for new HEAD; no live GLPI staging tests.
- Security: read-only and disabled by default; internal header authentication requires a trusted gateway; GLPI entity match is not an RBAC proof.
- Next: verify new HEAD CI, then run staging contract/RBAC tests with a scoped GLPI service account before any activation.

### 2026-11-09 — GLPI fail-closed upstream contract (#4)
- Branch / prior commit: `feat/observability-foundation` / `250b8ba6`.
- PR / issue: draft #1 / #4.
- Delivered: HTTPX mock-transport negative tests for upstream redirects, authorization failures, missing tickets, throttling, 5xx and non-JSON responses; documented generic error policy.
- Validation: GitHub Actions Python checks **passed** on `f814455f` (run 42674884849). New HEAD CI remains to be checked.
- Security: no redirects, no vendor error body propagation, no retries or ITSM mutations. Staging and RBAC qualification still blocked on real GLPI access.
- Next: confirm CI on new HEAD; qualify API version, token expiry and entity scope in staging.

### 2026-11-09 — GLPI origin validation regression tests (#4)
- Branch / commit before this handover: `feat/observability-foundation` / `eaf1de53`.
- PR / issue: draft #1 / #4.
- Delivered: negative tests verifying invalid GLPI origins are rejected before constructing an HTTP client (HTTP, embedded credentials, paths, query strings, fragments, localhost).
- Validation: GitHub Actions Python checks **passed** for `f6bbb894` (run 42675633942); check CI for new HEAD.
- Security: fixed HTTPS origin is necessary but insufficient; deployment still needs egress/DNS allowlisting and GLPI service-account RBAC validation.
- Next: inspect new HEAD CI, then stage real GLPI contract tests when a qualified environment is available.

### 2026-11-09 — GLPI bounded-response tests (#4)
- Branch / preceding commit: `feat/observability-foundation` / `1be8f073`.
- PR / issue: draft #1 / #4.
- Delivered: negative mock tests for oversized GLPI response bodies, invalid JSON, and array responses instead of an incident object.
- Validation: Python checks passed on `29ae65c9` (run 42675826400); new HEAD CI must be verified.
- Security: GLPI reads remain disabled by default and strictly read-only; staging version/ACL and service-token lifecycle remain unqualified.
- Next: confirm new CI, then stage API-contract and entity-permission tests.

### 2026-11-09 — GLPI staging qualification gate (#4)
- Branch / prior commit: `feat/observability-foundation` / `01b689f6`.
- PR / issue: draft #1 / #4.
- Delivered: `docs/GLPI-STAGING-QUALIFICATION.md` with prerequisite controls, expected results, evidence requirements, acceptance criteria and rollback; linked from adapter documentation.
- Validation: GitHub Actions Python checks **passed** on `3ea5ef51` (run 42676495843). Documentation HEAD CI should be rechecked.
- Security: no staging secrets, no real GLPI tests and no activation. Deployment must provide trusted gateway identity, egress ACL and read-only GLPI service-account RBAC.
- Next: obtain an approved GLPI staging environment, pin API version and run the qualification matrix; keep PR draft pending review.

### 2026-11-09 — GLPI snapshot cache policy (#4)
- Branch / prior commit: `feat/observability-foundation` / `9f74501f`.
- PR / issue: draft #1 / #4.
- Delivered: `Cache-Control: no-store` on successful authenticated GLPI incident snapshots, route-level regression test, adapter documentation.
- Validation: Python checks passed on `4ba36e94` (run 42676822911); verify new HEAD CI.
- Security: cache headers complement but do not replace gateway caching and logging policies. No staging GLPI qualification or ITSM mutation.
- Next: confirm CI and arrange GLPI staging RBAC/API tests; keep PR draft.
