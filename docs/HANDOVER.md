# AIOPS_GAMMA — Handover / session recovery

**Snapshot: 2026-11-12.** Read this first when taking over work, after a session interruption, or when changing developer/agent.

> **CURRENT SECURITY GATE — HOLD / NO_GO.** Draft PR #1 must not be merged or deployed. Do not activate LIVE, wire replay into `app/security.py` / `app/main.py`, or treat Gateway actor→tenant→resource ACL as qualified. Real PostgreSQL, HTTP and upstream authorization remain unqualified until executable evidence exists.

## Current working state
- Repo: https://github.com/alimtalbi-ata/AIOPS_GAMMA
- Active draft PR: https://github.com/alimtalbi-ata/AIOPS_GAMMA/pull/1
- Branch: `feat/observability-foundation`; `main` does **not** contain the feature branch.
- Historical branch HEAD at the previous replay CI review: `839feec3226321f3e3b6b41e3a67359ea41ff558`. The older green Python checks run `42679137227` was for an earlier commit and does **not** qualify current HEAD. Latest Python checks run `43123118315` and deployment contract run `43123118243` failed before evidenced step execution (`steps: null` for Python jobs). **Do not report pytest, Alembic or PostgreSQL qualification as passed.**
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

## Latest replay security/CI handover (2026-11-12)

- Branch `feat/observability-foundation`, draft PR #1: https://github.com/alimtalbi-ata/AIOPS_GAMMA/pull/1
- Commit `d2b6cfa47f591a3e70ffc64398b6df5f2f6dd61a`: four static regression checks in `tests/test_gateway_replay_rollout_hold.py` covering no replay-to-auth wiring, disposable PostgreSQL CI settings, and integration-test database safety gates. Source/AST guard review only; no new pytest execution claimed.
- Commit `839feec3226321f3e3b6b41e3a67359ea41ff558`: CI job `gateway-replay-postgres` now stages Alembic `upgrade head`, `downgrade 0001_initial`, `upgrade 0002_gateway_replay`, then database identity/revision/table checks before the real PostgreSQL concurrency tests. Confirmed command order from committed workflow blob; **not executed**.
- Python checks: https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43123118315 — `frontend`, `test`, and `gateway-replay-postgres` failed with `steps: null`. Deployment contract: https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43123118243 — failed. A prior replay job log download returned `404 BlobNotFound`. Root cause **not established**.
- **Operator action:** inspect the GitHub Actions run page banner/annotations and repository/org Actions policy, runner entitlement, usage/billing and approvals. Only after a runner actually starts should Alembic, pytest, concurrency and HTTP tests be evaluated. Record job steps, logs, migration results and connected database identity; do not infer green from static source.
- **Security gate:** no merge, deployment, LIVE remediation or replay authentication integration; external Gateway membership and actor→tenant→resource ACL must be independently qualified.

## Canonical read hard HOLD (2026-11-12)

- aiops draft review PR #668 (commit `fc970284bfcc991dbf146fe4fbec640d1ff2e14a`) documented reuse of #631 (Runs tenant groundwork), #246 (OIDC preflight) and #520 (signed GLPI xref/replay). Its Quality run `43128026513` completed SUCCESS; this is **not** real production IdP, resource ACL or GLPI actor authorization.
- GAMMA `app/reused/upstream.py` now unconditionally refuses `core`, `evidence` and `twin` canonical snapshot reads with HTTP 503 before any upstream network access. The former provisional transport was removed from the active function. An echoed tenant ID and service bearer are not authorization.
- `tests/test_upstream.py` now requires denial and zero upstream HTTP for all three resources even with `enable_canonical_reads=True` and configured token/origins. Unknown resources still return 404; fixed HTTPS origin validator tests remain.
- `docs/CANONICAL-READ-ADAPTER.md` records the hard HOLD and the prerequisite independent actor→tenant→resource ACL for Core/Evidence/Twin. No provider was assumed; no migrations, LIVE/HITL, replay authentication wiring, or Debian operations.
- This change is a **code safety fence**, not a qualified canonical read integration. Verify new exact-head CI before claiming pytest passed; GitHub Actions runner failures with `steps: null` are not test failures.

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
- General PromQL metrics API returns 501; OpenSearch query mapping must be checked against actual upstream pipeline. LLM KPI preview is implemented but uses caller-supplied samples; Sentinel/ArgusLM live connectors and trustworthy time-series/SLOs are not integrated.
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

### 2026-11-09 — GLPI configuration fail-closed tests (#4)
- Branch / preceding commit: `feat/observability-foundation` / `bcfc1139`.
- PR / issue: draft #1 / #4.
- Delivered: mock tests proving missing GLPI URL/entity/service credentials and invalid entity identifiers fail before any HTTP client construction.
- Validation: Python checks for `e86e0041` were in progress (run 42677594572) when checked; inspect CI on latest HEAD before treating it as validated.
- Security: no credentials committed; GLPI read remains feature-flagged off by default and requires staging RBAC/API qualification.
- Next: confirm CI; arrange approved GLPI staging service account and execute `docs/GLPI-STAGING-QUALIFICATION.md`.

### 2026-11-09 — shared HTTPS origin port validation (#2/#4)
- Branch / preceding commit: `feat/observability-foundation` / `bf7b4c7e`.
- PR / issues: draft #1 / #2, #4.
- Delivered: reject malformed, zero and out-of-range ports in the shared `validate_origin` guard before network access; add regression tests for both canonical and GLPI adapters.
- Validation: Python checks for `a278e2a7` were in progress when checked (run 42677740871); recheck CI on the latest HEAD.
- Security: validation remains necessary but insufficient without infrastructure DNS/egress allowlists, TLS and tenant RBAC. No staging GLPI qualification or ITSM writes.
- Next: confirm new HEAD CI; execute approved GLPI staging qualification matrix when infrastructure is available.

### 2026-11-09 — Sentinel + ArgusLM LLM KPI contract (#3)
- Branch / preceding commit: `feat/observability-foundation` / `cd9ae207`.
- PR / issue: draft #1 / #3 (observability and measurement).
- Source repos examined: `alimtalbi-ata/sentinel-llm` (`main`) metric names, Prometheus handler and scrape config; `alimtalbi-ata/arguslm-llm` (`master`) TTFT/TPS/cost estimator, uptime and benchmark APIs.
- Delivered: tenant-bound, non-authoritative `POST /api/v1/observability/llm/kpis/preview`, typed finite value validation, explicit millisecond/USD units, percentiles and coverage, tests for missing values/tenant isolation, `docs/LLM-KPI-CONTRACT.md`.
- Validation: previous Python checks passed at `13c91696` (run 42677877051); new HEAD CI must be checked.
- Security: caller samples are not trustworthy source telemetry. No live API calls, ingestion, credentials, persisted facts, GLPI mutation or LIVE remediation.
- Next: qualify tenant-scoped source connectors and implement timestamped persistence; establish SLO/sample size criteria before dashboards.

### 2026-11-09 — documentation consolidation: GLPI, ITIL 4 and LLM KPI
- Branch / preceding commit: `feat/observability-foundation` / `28625290`.
- PR: draft #1; related issues #2/#3/#4.
- Delivered: refreshed root README (actual package version 0.2.0, endpoint inventory and sample KPI request), `docs/PROJECT-STATUS.md` (capability matrix and blockers), `docs/ROADMAP.md` (K0–K5 KPI milestones), `docs/LLM-KPI-CONTRACT.md` (worked example, partial coverage and authorization caveats), and this handover.
- Validation: implementation commit `73ab1335` passed Python checks ([run 42679137227](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/42679137227)). Recheck CI for the **documentation HEAD**; no live Sentinel, ArgusLM or GLPI staging tests.
- Security/ownership: KPI input is caller-supplied and non-authoritative, model ID not independently ACL-verified, ITSM remains system-of-record, no LIVE actions or ticket writes. GLPI read-only disabled by default.
- Next: qualified tenant-scoped Sentinel/ArgusLM source adapters, provenance and timestamped KPI history, SLO dashboards after data validation; execute GLPI staging qualification independently. Keep PR draft.

### 2026-11-09 — evidence-first platform UX design
- Branch / prior commit: `feat/observability-foundation` / `213886cb`; PR #1 remains draft.
- Delivered: `docs/PRODUCT-UX-DESIGN.md` inspired by four user-provided DEV articles. Specifies incident-centric navigation, KPI provenance and sample quality, evidence-based RCA, structured code search, ITSM ownership, safe Policy/HITL and UX0–UX5 acceptance gates. Linked from README and ROADMAP.
- Validation: prior documentation HEAD `fe1e6279` CI status must be checked separately; current UX work is documentation-only and requires CI on latest HEAD.
- Security: no new frontend functionality, live telemetry, staging qualifications, ITSM writes, untrusted agent tools or LIVE execution.
- Next: implement UX0/UX1 in React with explicit synthetic and non-authoritative KPI states, then test frontend build and accessibility; keep PR draft.

### 2026-11-09 — fifth AI SRE design reference and effectiveness KPIs
- Branch / preceding commit: `feat/observability-foundation` / `cda68050`; draft PR #1.
- Reviewed: Siddharth Singh, [AI SRE: The Complete Guide for Engineering Teams in 2026](https://dev.to/siddharth_singh_409bd5267/ai-sre-the-complete-guide-for-engineering-teams-in-2026-51ba).
- Delivered: UX blueprint adds a read-only multi-step investigation run, hypothesis evidence and critic states, postmortem draft, L0–L4 autonomy ladder, one-service shadow-mode pilot and proposed RCA-quality/time-to-RCA/tool-safety KPIs. Roadmap updated.
- Validation: Python checks passed for prior HEAD `9bcbf777` (run 42681053786). Recheck latest documentation HEAD.
- Not implemented: investigation agent, process KPI telemetry, live source connectors, automated postmortem, or production execution. No vendor performance claims independently verified.
- Next: build bounded investigation-run schema and offline evaluation fixtures; keep separate from the Sentinel/ArgusLM model-performance KPI preview.

### 2026-11-09 — evidence-linked RCA investigation preview
- Branch / preceding commit: `feat/observability-foundation` / `02cfea8f`; draft PR #1.
- Delivered: `app/reused/investigation.py`, authenticated `POST /api/v1/incidents/investigation/preview`, strict source/time/ref validation, cross-tenant denial, offline tests and `docs/INVESTIGATION-PREVIEW.md`.
- Validation: Python checks green on previous `9bcbf777` (run 42681053786); recheck CI on new HEAD. No external telemetry or staging tests performed.
- Security: references resolve only within caller-supplied request; **not** source attestation or confirmed RCA. No tool calls, persistence, ITSM mutation or LIVE remediation.
- Next: qualify trusted source-bound evidence, investigation step receipts and human-adjudicated RCA process KPI fixtures before UI live-data claims.

### 2026-11-09 — target architecture and repository reuse inventory
- Branch / preceding commit: `feat/observability-foundation` / `84130232`; PR #1 remains draft.
- Reviewed: 20 accessible repositories inventoried; trees of 10 technical repositories inspected, with primary code/docs examined for aiops, observability-stack, aurora, holmesgpt, akmatori, incidentfox, sentinel and arguslm.
- Delivered: `docs/TARGET-ARCHITECTURE-2026.md` (domain ownership, target topology, contracts, four operational flows, deployment zones, P0–P6 gates) and `docs/REUSE-COMPONENT-INVENTORY.md` (path-level candidates, priorities, reuse/avoid decisions, integration qualification).
- Validation: documents-only changes; latest HEAD CI must be checked. No staging integrations, license audit, live credentials or autonomous execution performed.
- Next: freeze upstream SHAs/licenses, approve one investigation engine, qualify tenant-authenticated read-only source contracts and validate staging GLPI independently.

### 2026-11-09 — mandatory dual deployment architecture
- User requirement: **every GAMMA-operated platform component** must support both Docker Compose and Kubernetes/Helm from versioned OCI images; externally managed GLPI/SSO/SaaS may remain external, but their connectors must be deployable in both environments.
- Delivered: `docs/DEPLOYMENT-CONTRACT.md` with component matrix, profiles, target folder structure, OCI packaging, CI stages, network/tenant/secrets/volume constraints and acceptance checklist; linked from target architecture, reuse inventory, roadmap and README.
- Status: documentation-only decision. No new Compose/Helm manifests or staging qualification claimed. Keep draft PR #1; check latest HEAD CI.

### 2026-11-09 — initial Compose/Helm deployment manifests
- Branch: `feat/observability-foundation`, PR #1 draft. Existing root Compose and API/UI Dockerfiles reused.
- Delivered: `deploy/compose/compose.yaml`, `deploy/compose/.env.example`, `deploy/helm/gamma` (Chart, values, API/UI Deployments/Services, optional Ingress, scoped ingress NetworkPolicies), `deploy/README.md`, `.github/workflows/deployment-contract.yml` (static Compose/Helm checks).
- Safety: existing API internal key and DB DSN are Kubernetes Secret refs; default feature flags off; API runs non-root; no namespace-wide deny that could disrupt unrelated pods.
- Known blockers: UI nginx currently serves static SPA only (no authenticated `/api` proxy); chart does not provide full database/Temporal/Core/observability/KPI stack; probes are TCP-only; no tested image digests, staging TLS/SSO, full network egress or production readiness. Do not claim complete platform deployment.
- Validation: new HEAD CI pending; Compose/Helm syntax and runtime staging tests not independently executed in this session. Check workflow results and fix failures before promotion.

### 2026-11-09 — monodirectory and rootless deployment requirement
- User requirement: keep GAMMA application installation and persistent data under one configurable `GAMMA_HOME`, no host writes in `/bin`, `/sbin`, `/var`, `/tmp`, with rootless container runtime and non-root Kubernetes workloads.
- Delivered: `docs/ROOTLESS-SINGLE-DIRECTORY.md`, optional `deploy/compose/compose.rootless.yaml` with bind-mounted Postgres/OpenSearch data and dropped capabilities, `deploy/scripts/check-rootless-home.sh` (non-mutating preflight), plus deployment/architecture/roadmap/README updates.
- Critical limitations: rootless daemon's own XDG paths and system prerequisites, Linux image internal paths, Kubernetes runtime/CSI paths are not automatically confined; Nginx UI image and upstream services are not yet rootless qualified. No runtime smoke or host-path audit performed. Do not claim completed compliance.
- Next: use a disposable rootless host, pin runtime data-root under GAMMA_HOME, test UID/GID and every mount, rebuild nginx as non-root, qualify K8s restricted and audit filesystem writes.

### 2026-11-09 — non-root UI deployment increment
- Updated `frontend/Dockerfile` to unprivileged Nginx UID/GID 101; `frontend/nginx.conf` listens on 8080; root Compose maps host 5173 to container 8080; Helm UI uses port 8080 and enforces runAsNonRoot/101/seccomp.
- Rootless preflight now rejects Docker data-root outside `GAMMA_HOME/docker-data`; CI validates rootless overlay Compose config, preflight syntax, builds UI image, checks UID and Nginx configuration.
- Limitations: no actual rootless daemon startup or Kubernetes staging qualification performed in this session; CI on new HEAD to check. No proof of all-container single-directory installation or full read-only root filesystems. PR #1 remains draft.

### 2026-11-09 — CI fix for rootless Compose overlay
- Previous commit `51fc0364`: Python checks passed; deployment contract failed only in Compose rootless overlay validation; UI image and Helm jobs passed.
- Root cause from job logs: duplicate `services.api.security_opt` entry after overlay merge (`no-new-privileges:true`). Removed duplicate security_opt from optional rootless overlay; base security overlay retains it for API and frontend.
- CI extended to assert rendered Compose JSON bind mounts under GAMMA_HOME and non-root API/relay users. No real rootless runtime smoke test yet. Check new HEAD workflow before declaring CI green.

### 2026-11-09 — rootless Compose audit and profile-aware CI fix
- CI on `02694b30`: Python, UI image, Helm and Compose YAML checks passed; static contract assertion failed with `KeyError: 'opensearch'` because Compose omits services behind disabled profiles. CI now enables `--profile relay --profile observability-demo` for assertions.
- Added `deploy/scripts/audit-rootless-compose.sh`, a read-only inspection of running containers for configured non-root users, privileged mode and bind mounts under GAMMA_HOME. It deliberately fails on named volumes or unspecified users, and requires a real rootless Docker host.
- No rootless Docker host was available through GitHub connector; do not claim live smoke testing, complete compliance or CI success until workflow results confirm.

### 2026-11-09 — opt-in rootless startup smoke
- Confirmed on HEAD `ff995e86`: Python checks and Deployment contract (static) both successful.
- Added `deploy/scripts/smoke-rootless.sh` for **manual** rootless baseline UI/API/Postgres startup, localhost UI HTTP probe and runtime mount/privilege audit; CI syntax-checks the shell scripts.
- The smoke script has **not been executed** against a real rootless host; upstream PostgreSQL configured UID and bind-mount ownership are unresolved and may cause an intentional audit failure. No OpenSearch/Temporal/Sentinel/ArgusLM/K8s end-to-end validation. Keep PR draft.

### 2026-11-09 — harden rootless filesystem guardrails
- Both Python and static Deployment contract workflows succeeded for `5f73d88e`.
- Strengthened preflight: require GAMMA_HOME ownership and reject symlink escapes in Docker data-root and persistent bind directories.
- Runtime audit now checks stopped containers as well; added offline mocked-Docker preflight tests to CI.
- No real rootless host or Kubernetes staging test executed. The new CI results must be checked before declaring them green.

### 2026-11-09 — offline preflight test fixture correction
- CI on `00f2e586`: Python passed, Helm passed, UI image passed, Compose static validation passed; offline preflight unit test failed because `tempfile.TemporaryDirectory()` created the positive test root under `/tmp`, which the production preflight deliberately forbids.
- Moved the fixture to the CI user's home directory (and included stderr in assertion). This is a test correction, **not** a relaxation of the forbidden system path contract.
- Await CI on new HEAD. Actual rootless Docker Compose runtime smoke remains unexecuted.

### 2026-11-09 — live UI container smoke in CI
- CI on `c9b5b60c`: Python checks and Deployment contract both passed.
- Added a GitHub Actions UI runtime test that starts the built image as UID 101 with all capabilities dropped, checks HTTP on localhost:18080, verifies running/unprivileged state, and cleans up the test container.
- CI result on new HEAD pending. This is **not** Docker Engine rootless and does not validate PostgreSQL/OpenSearch, full-stack startup or Kubernetes staging.

### 2026-11-09 — PostgreSQL + API Compose runtime smoke
- On `1aa47f90`, Python checks and Deployment contract (including real non-root UI HTTP smoke) succeeded.
- Added a separate GitHub-hosted CI job that starts PostgreSQL + API, waits for readiness, probes API health, inspects configured API user and privilege state, then captures logs and removes containers/volumes.
- New job result pending. The test is **not** a Docker rootless runtime validation and does not cover the optional OpenSearch profile or Kubernetes end-to-end.

### 2026-11-09 — bind-mounted baseline CI smoke
- On `4d9f1e40`, both GitHub workflows succeeded, including the PostgreSQL+API Compose runtime job and the non-root UI runtime smoke.
- Added a CI job for full baseline UI/API/PostgreSQL with `GAMMA_HOME/data/postgres` bind mount, HTTP probes and actual mount inspection. It runs on the GitHub-hosted Docker daemon, **not** rootless. CI result on this new commit pending.
- The rootless-engine data-root, PostgreSQL UID ownership and full-stack K8s deployment still need dedicated runtime qualification.

### 2026-11-09 — PostgreSQL bind mount capability regression
- CI on `9ab03786`: Python, Helm, Compose static, UI runtime and normal PostgreSQL/API runtime succeeded. The new single-directory bind-mount runtime job **failed**.
- Logs: `chmod: /var/lib/postgresql/data: Operation not permitted`, `chmod: /var/run/postgresql: Operation not permitted`, `chown: /var/lib/postgresql/data: Operation not permitted`. Root cause: `cap_drop: [ALL]` prevents upstream PostgreSQL entrypoint setup.
- Added narrowly scoped `CHOWN`, `FOWNER`, `DAC_OVERRIDE` for PostgreSQL in rootless overlay while keeping `cap_drop: [ALL]`. New CI status pending. This does not certify rootless Docker or non-root initialization.

### 2026-11-09 — PostgreSQL UID transition follow-up
- On `f7956bb1`, Python, Helm, UI, Compose static and normal API/PostgreSQL runtime succeeded; single-directory bind mount still failed.
- New log: `error: failed switching to 'postgres': operation not permitted`. Previous `CHOWN`/`FOWNER`/`DAC_OVERRIDE` adjustment resolved the initial chmod/chown errors but prevented the upstream entrypoint's UID/GID transition.
- Added `SETUID` and `SETGID` to PostgreSQL-only `cap_add` while retaining `cap_drop: ALL`. Await fresh CI; rootless host certification remains open.

### 2026-11-09 — baseline bind-mount startup reached readiness probes
- On `baf5be68`, Python, Helm, Compose static, UI and regular PostgreSQL/API jobs succeeded. The single-directory baseline job **started all three containers successfully**, including PostgreSQL on the bind mount.
- The probe step failed immediately with `curl: (56) Recv failure: Connection reset by peer` just after startup. Since UI/API have no Compose healthchecks, `up --wait` does not guarantee their HTTP readiness; changed the CI job to retry both HTTP probes for up to approximately 60 seconds before failing.
- New CI pending. This does not qualify a rootless Docker daemon; no live PostgreSQL restart/persistence test yet.

### 2026-11-09 — PostgreSQL bind persistence after recreation
- On `18f2e8a6`, Python and all Deployment contract jobs passed, including UI/API/PostgreSQL baseline bind-mount runtime smoke.
- Extended `single-directory-runtime` to create/write a PostgreSQL sentinel table, remove/recreate its container, verify the persisted value and assert the bind path remains under `GAMMA_HOME`.
- Await new CI result. This is not an actual rootless-engine test, nor does it establish backup/restore, image digest pinning or full Kubernetes parity.

### 2026-11-09 — PostgreSQL logical backup/restore rehearsal
- `6d9e3468` passed Python and all Deployment contract jobs, including PostgreSQL sentinel persistence across container recreation with a bind mount under `GAMMA_HOME`.
- Added CI-only logical `pg_dump` to `GAMMA_HOME/backups`, checked 0700/0600 permissions and ownership, dropped disposable sentinel table, restored via `psql`, and verified the sentinel record.
- New CI result pending. This is not a rootless host certification or a production backup strategy.

### 2026-11-09 — backup/restore green, rootless smoke hardened
- `3783aeca`: both GitHub Actions workflows succeeded, including the PostgreSQL logical backup/restore rehearsal under `GAMMA_HOME/backups`.
- Updated optional dedicated-host `smoke-rootless.sh` to require curl, retry UI/API HTTP readiness, check `pg_isready`, then run the strict rootless runtime audit.
- No rootless host was available or tested; upstream PostgreSQL configured-root user still blocks strict audit until resolved. New commit CI pending.

### 2026-11-09 — PostgreSQL runtime UID assertion
- Both workflows passed on `18ae32ee`.
- Added a CI runtime assertion that PostgreSQL PID 1's effective UID is nonzero in the single-directory bind-mount job, and fixed Compose capability comment formatting.
- This checks the running process, not the upstream image's configured user. The strict rootless audit still intentionally rejects an unspecified/root configured user; no rootless Docker host test has been run. New CI pending.

### 2026-11-09 — strict dual-identity rootless audit
- `0ac0fceb`: both Python and deployment workflows succeeded, including PostgreSQL PID 1 non-root assertion on a non-rootless runner.
- Rootless audit now checks both configured container user and live PID 1 UID, failing closed on unavailable/invalid/root UID without waiving an unspecified configured user. PostgreSQL's upstream configured-user mismatch remains an open rootless gate.
- New CI pending; no actual rootless Docker daemon qualification performed.

### 2026-11-09 — mocked strict rootless audit contract tests
- `421a2b0a`: Python and deployment workflows both passed.
- Added offline tests for `audit-rootless-compose.sh` using mocked Docker: non-root configured/runtime UID success; root/empty configured user and root/invalid runtime UID failures.
- Wired these tests into deployment Compose CI. These tests do **not** run Docker rootless and do not establish PostgreSQL rootless compatibility. New CI pending.

### 2026-11-09 — extended rootless audit regression coverage
- `00468b2d`: both Python and deployment CI workflows passed, including mocked Docker rootless audit tests.
- Extended mocked audit regression cases to reject privileged containers, stopped containers, bind mounts outside `GAMMA_HOME/data`, and Docker named volumes.
- CI on the new commit is pending; these are simulated contract tests, not rootless-engine runtime qualification.

### 2026-11-09 — rootless bind source canonicalization
- `bac40a8e`: Python and deployment workflows passed, including expanded mocked rootless audit checks.
- Strict audit now resolves each bind source with `pwd -P` and rejects symlink escapes and missing directories; added offline regression tests.
- New CI pending. No real rootless Docker host test has been performed.

### 2026-11-09 — rootless bind ownership and mode gate
- `79fe81e3`: Python and deployment workflows passed, including symlink escape and missing bind source regression tests.
- Rootless runtime audit now checks host-visible UID ownership and rejects group/world writable bind directories; added mocked Docker tests for modes 0770 and 0777.
- Rootless PostgreSQL UID mapping may conflict with host-visible ownership requirements; treat as an unresolved compatibility gate. New CI pending.

### 2026-11-10 — rootless qualification evidence collector
- `598c1106`: Python and deployment workflows passed, including owner/mode negative tests.
- Added `deploy/scripts/inspect-rootless-evidence.sh`, a read-only diagnostic to capture Docker rootless preflight, host UID/GID, canonical data directory ownership/modes, configured user, PID 1 UID, privileged/running state, and mount sources. Does not change runtime or bypass strict audit.
- Must run on an actual disposable rootless host; current CI remains GitHub-hosted rootful Docker plus offline mocks. New CI pending.

### 2026-11-10 — CI wiring audit correction
- `8a8ddfa7`: both workflows passed, but inspection of the deployment workflow revealed that `test-rootless-audit.py` was **not actually invoked** by CI, despite prior handover claims. Previous green runs therefore did not validate this test suite.
- Added an explicit CI step to run `python3 deploy/scripts/test-rootless-audit.py -v` and syntax-check `inspect-rootless-evidence.sh`.
- Treat new CI as the first authoritative execution of the mocked audit suite; failures must be fixed before claiming it passes. Rootless daemon qualification remains outstanding.

### 2026-11-10 — configured UID zero bypass hardening
- `b8a6acdd`: both workflows passed, now including the previously missing mocked strict audit suite.
- Fixed audit acceptance of numeric root user forms such as `0:1000` and `00:1000`. Require explicit numeric nonzero configured UID, rejecting unresolvable named users; runtime PID 1 UID remains separately verified.
- Added tests for numeric UID zero variants, named users and leading-zero nonroot numeric UIDs. New CI pending; no actual rootless Docker qualification.

### 2026-11-10 — configured GID and runtime UID hardening
- `d1b98b46`: Python, Compose, Helm, UI, and API/PostgreSQL jobs passed; single-directory-runtime was still running when checked.
- Audit now rejects malformed configured numeric GIDs (empty, named, multiple colons) and zero-padded runtime UID 000, with offline regression tests.
- New CI pending; genuine rootless Docker engine and PostgreSQL qualification remain outstanding.

### 2026-11-10 — fail-closed disposable rootless smoke
- Added explicit `GAMMA_ROOTLESS_SMOKE_DISPOSABLE=YES` opt-in and refuse nonempty `GAMMA_HOME/data/postgres` before Docker Compose startup.
- New directories are created with restrictive umask; no permission changes to existing directories, no data deletion or cleanup.
- CI for the new change is pending. This is not a rootless runtime qualification.

### 2026-11-10 — offline disposable smoke guard regression tests
- Added `deploy/scripts/test-rootless-smoke.py` and wired it into deployment CI. Mock Docker tests verify absent/wrong disposable opt-in blocks Compose, existing hidden PostgreSQL data is preserved and blocks Compose, and a fresh opted-in directory reaches Compose (mock exits intentionally).
- `a56a062b` CI was in progress when checked. New CI for these tests is pending; no rootless daemon qualification has been performed.

### 2026-11-10 — rootless smoke Compose project collision guard
- `8a9e561b`: Python and deployment CI passed, including disposable smoke mock tests.
- Rootless smoke now rejects any pre-existing Compose project containers before startup, and a new offline mock test covers the refusal.
- CI for this change pending. Existing project inspection is non-atomic; dedicated isolated host remains required.

### 2026-11-10 — rootless smoke port collision guard
- `1af01c2c`: Python and deployment CI both passed, including Compose project collision tests.
- Added Python stdlib loopback bind preflight for ports 5173 and 8000 before rootless Compose startup, with mocked-socket tests wired into deployment CI.
- Preflight is non-atomic and does not substitute for an isolated host; new CI pending, real rootless qualification outstanding.

### 2026-11-10 — PostgreSQL rootless fail-fast gate
- `3b9f4511`: Python and deployment CI both succeeded.
- Rootless smoke now validates PostgreSQL's rendered configured numeric non-root UID **before** any `compose up`. The current official PostgreSQL Compose overlay is intentionally rejected, preventing an unqualified root-configured container from initializing data.
- Offline unit tests and mocked smoke startup use a qualified test-only PostgreSQL user; wired into deployment CI. New CI pending; real rootless PostgreSQL compatibility remains unproven.

### 2026-11-10 — isolated PostgreSQL non-root experiment
- `d4bff1ea`: Python and deployment CI passed.
- Added opt-in `deploy/compose/compose.postgres-nonroot.experimental.yaml` with PostgreSQL UID/GID 10001, PGDATA subdirectory and no capabilities, plus static Compose contract CI. Existing rootless overlay and runtime tests remain unchanged.
- Important blocker: rootless Docker UID mapping can make user-owned 0700 bind data inaccessible to UID 10001. No rootless PostgreSQL runtime initialization or persistence has been demonstrated; new CI pending.

### 2026-11-10 — experimental PostgreSQL Compose capability merge fix
- `cfd466fd`: Python checks succeeded; deployment contract failed in the experimental PostgreSQL static job. Rendered `cap_add` incorrectly retained CHOWN/FOWNER/DAC_OVERRIDE/SETUID/SETGID because `cap_add: []` did not reset the earlier overlay.
- Replaced with `cap_add: !reset []`; static CI continues asserting the rendered effective capability additions are empty. New CI pending.
- No rootless runtime qualification or production deployment.

### 2026-11-10 — disposable PostgreSQL non-root runtime CI experiment
- `ffe09ef1`: Python, Compose, Helm, UI and API/PostgreSQL jobs passed; single-directory runtime still running when checked.
- Added separate `postgres-nonroot-experiment` job to start experimental PostgreSQL as UID 10001, verify effective capabilities and runtime UID, and perform a SQL write on rootful GitHub Docker.
- Uses disposable world-writable bind **only in isolated rootful CI**, not acceptable for rootless production. New CI pending; rootless UID mapping and secure bind permissions remain blockers.

### 2026-11-10 — PostgreSQL non-root persistence rehearsal
- `aeb7a95e`: Python and deployment CI both succeeded, including rootful Docker non-root PostgreSQL startup and SQL write.
- Extended the isolated experimental job to assert `pgdata` is owned by UID 10001 with mode 0700, recreate the PostgreSQL container and verify SQL row persistence.
- New CI pending. Rootless user namespace mapping and strict host bind ownership remain unverified.

### 2026-11-10 — private disposable PostgreSQL bind in rootful CI
- `cadcd569`: both workflows succeeded, including PostgreSQL non-root PGDATA ownership/mode and persistence across recreation.
- Replaced the experimental job's world-writable PostgreSQL parent with a disposable UID 10001-owned, mode 0700 bind; ownership transfer uses `sudo` **only on the disposable GitHub Actions rootful runner**, never in the GAMMA installer.
- New CI pending. This rootful setup is not compliant with the rootless audit requirement that host binds remain owned by the invoking user; UID namespace mapping remains unresolved.

### 2026-11-10 — GitHub Actions billing block (confirmed by UI annotations)
- Workflow run `42803654371` did not execute any of its six jobs. GitHub explicitly reports: "The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings". The Python checks run was also blocked with zero executed steps.
- This is an account billing/spending-limit gate, **not evidence of a code or PostgreSQL test failure**. Earlier rootful non-root PostgreSQL checks on `cadcd569` succeeded. Current HEAD `22d3b9ec` is **not CI-qualified**; its private-bind change remains untested.
- Do not retry workflows or change CI/Docker configuration to circumvent billing restrictions. Account owner should resolve the billing/spending limit in GitHub Settings > Billing & Licensing and then rerun CI; preserve the PR in draft, with no merge/deploy.
- The `ubuntu-latest` migration notice (Ubuntu 26) is separate and is not the cause of these failures.

### 2026-11-10 — fail-closed PostgreSQL effective capability preflight (CI billing blocked)
- Extended `deploy/scripts/check-postgres-rootless.py` to reject effective Compose PostgreSQL configurations with any inherited `cap_add` or without `cap_drop: [ALL]`, in addition to requiring numeric non-root UID. This catches Compose overlay merge behavior that silently retained capabilities.
- Updated offline unit cases and rootless smoke mock to cover the hardened preflight. The baseline rootless smoke remains intentionally blocked by upstream root-configured PostgreSQL; the experimental override is not automatically enabled.
- GitHub Actions billing restriction remains unresolved as last observed. These changes are **not CI-validated**; run the offline tests and full CI when runners are restored. No rootless host runtime qualification, merge, or production deployment.


## 2026-11-12 — upstream tenant ACL compatibility audit (#2)

- Inspected exact source blobs in `alimtalbi-ata/aiops`: Core `43b61a08d4dd099c7c28ee0d73e5a3e1f681cdca`, Evidence `c581d407c8e84de87acbdf749a4e2aa8f052dedf`, Twin `e098ec039b5f352f537ed8985e721067a1386508`.
- **Blocking finding:** inspected Core/Evidence/Twin route handlers do not establish per-resource tenant authorization. Core uses a shared internal token; Evidence and Twin GET routes inspected show no tenant principal/filter. Core route paths also differ from GAMMA's provisional `/api/v1/...` adapter paths. An imported helper name is not proof of route enforcement.
- GAMMA canonical adapter blob `e7a34575a02803de243c56b8d69ed4910c8d7943` has useful transport controls (fixed HTTPS origins, GET-only, no redirects/proxy, TLS, timeout, 256 KiB bound), but its tenant echo check is not upstream ACL. Keep `ENABLE_CANONICAL_READS=false`.
- Added `docs/AIOPS-UPSTREAM-ACL-AUDIT.md` at commit `70fae1d1699c7d42079fcad14a9276fda792d219`, recording exact blobs, route mismatches, reuse boundaries and required gates.
- Reuse review: `aiops` remains canonical incident/Policy/Evidence/Twin owner; `observability-stack` is the OTel/Data Prepper/OpenSearch/Cortex candidate; Aurora/HolmesGPT/Akmatori/IncidentFox remain shadow-mode investigation candidates only. No large upstream project copied and no tool executor enabled.
- Validation: source inspection and documentation commit only. No upstream runtime, PostgreSQL multi-tenant or HTTP integration test executed; no ACL qualification claimed.
- Next: repair tenant identity/membership and resource query filtering in the canonical `aiops` services, with two-tenant tests, before changing GAMMA adapters. Preserve draft PR and HOLD / NO_GO.


### CI observation after audit documentation — HEAD `7e0fbeeabcc615777058e91f7119f5974ef8987a`

- GitHub Actions runs `43126704922` (Python checks) and `43126704841` (deployment contract) both concluded `failure`.
- All reported jobs have `steps: null`; job-log retrieval for representative Python and Helm jobs returned `404 BlobNotFound`. Therefore the failure stage/root cause remains **unknown**; do not attribute it to code, tests, runner policy or billing without evidence.
- No pytest, frontend build, Helm validation, Compose smoke, Alembic or PostgreSQL test pass is claimed for this HEAD.
- Operator follow-up remains: inspect Actions run UI/annotations and repository/org Actions runner/usage policy; obtain a run where job steps actually execute before assessing test results.

### 2026-11-12 — legacy canonical test alignment

- Exact previous HEAD `00d3efea897966b2234d6d3b0c96b23c2888a68f`: Python checks run `43185367060` and deployment contract run `43185366913` both concluded FAILURE. Every inspected job reported `steps: null`; therefore no pytest/Helm/frontend/PostgreSQL step execution is evidenced and root cause remains unknown.
- Updated legacy canonical HTTP-mock suites `test_upstream_http_mock.py`, `test_upstream_transport_boundary.py`, and `test_upstream_fail_closed_extra.py` to assert 503/no network for canonical reads instead of obsolete successful tenant-echo/502 transport behavior. GLPI cases were not deliberately changed.
- Added `tests/test_canonical_acl_hard_hold_static.py` to guard the exact fail-closed canonical adapter AST shape (allowlist 404 then unconditional 503; no await or return). This is source-level regression coverage, not real upstream ACL qualification.
- Current HEAD CI and runtime tests remain to be checked; no production access, merge, deploy, replay authentication wiring or LIVE action performed.

### 2026-11-12 — canonical route HTTP HOLD regression

- Previous HEAD `10595a9f9c54284272cd01ca4282aaad7807ff8c` GitHub Actions Python run `43185641514` and deployment contract run `43185641672` both failed. All nine inspected jobs returned `steps: null`; no test step or log-based root cause is established.
- Added `tests/test_canonical_route_http_hold.py` against the real `app.main` FastAPI route, with a locally signed request-bound gateway assertion. Parametrized Core/Evidence/Twin cases assert 503 even with the canonical feature flag enabled and a configured service token, plus no network and `Cache-Control: no-store`. Key-only/forged identity and `tenant_access=false` must return 401; unknown resource with valid assertion must return 404.
- These are in-repository HTTP test definitions; no pytest execution or real upstream/IdP/PostgreSQL qualification is claimed until an executable runner produces results.
- Reuse boundary remains: `aiops` PR #631 Runs-only groundwork, #246 actor introspection candidate, #520 GLPI signed xref candidate; no assumptions about the real IdP.

### 2026-11-12 — two-tenant HTTP SQL-boundary tests (no PostgreSQL)

- Previous HEAD `f251cbaa20ad09f5377ebc8ed5d1e68fe2f48ddf`: Python run `43188533806` and deployment contract run `43188533953` both failed with all nine jobs `steps: null`. No test step execution or failure root cause established.
- Added `tests/test_resource_list_http_tenant_isolation.py` against the real FastAPI GET topology binding and incident evidence routes. A signed Gateway principal for tenant A/B is deliberately paired with a forged opposite `X-Tenant-ID` and `X-Actor-ID`. A dependency-injected SQLAlchemy statement spy asserts the exact bound tenant filter, evidence incident filter, 500-row limit, and per-tenant response separation; it also checks `Cache-Control: no-store`.
- This is a two-tenant **HTTP + SQL-expression** regression using in-memory rows and a fake session. It is **not** a real PostgreSQL transaction, RLS, real actor membership or upstream Core/Evidence/Twin ACL test. Do not use it as a release gate substitute for disposable PostgreSQL 16 and real identity qualification.
- No merge, deployment, LIVE, replay-auth wiring, Debian operation or production database access performed.

### 2026-11-12 — CI pre-step root-cause triage

- Exact prior HEAD `15a021285953fa3c613cc2837c03125f550c2c11` Python run `43191691027` and deployment contract run `43191691038` failed. All nine jobs returned `steps: null`. Independent step fetch for three Python jobs returned `[]`; independent job-log fetch for the same jobs returned HTTP 404 `BlobNotFound`.
- Added `docs/GITHUB-ACTIONS-PRESTEP-TRIAGE-20261112.md` with exact run/job IDs, observed evidence, operator UI/policy/billing/runner/status/support checks, and required acceptance evidence. `BlobNotFound` is not asserted as the root cause.
- No speculative workflow changes, job retries, test success claims, deployment, production database or Debian operations. HOLD / NO_GO remains.

### 2026-11-12 — ChatGPT isolated lab requested

- Added `docs/CHATGPT-LAB-TEST-REPORT-20261112.md`: disposable Python 3.13.5 lab ran a reconstructed **subset** of exact GitHub adapter/static-test source with a stub settings module and lab-only runtime checks. Command `python -m pytest -q tests/test_canonical_acl_hard_hold_static.py tests/test_canonical_lab.py` yielded **5 passed in 0.23s**.
- Private GitHub repo could not be cloned in the lab (DNS/network unavailable); full repository, real FastAPI route, PostgreSQL 16, frontend, Helm, Docker and IdP/ACL tests **not** executed. This is not a GitHub Actions replacement or production qualification.
- Existing GitHub Actions workflows preserved; a permanent runner requires separately provisioned infrastructure. HOLD / NO_GO unchanged.

### 2026-11-12 — reproducible bounded ChatGPT lab runner

- Added `scripts/run_bounded_lab.py` with a fixed ten-file source-only pytest allowlist, incomplete-checkout checks, inherited database/replay environment guard, exit-code preservation and optional JSON report outside the checkout. See `docs/BOUNDED-CHATGPT-LAB-RUNNER.md`.
- The runner requires a real checkout and installed dependencies. It is **not yet executed** against a complete GAMMA checkout. It cannot replace persistent GitHub Actions, PostgreSQL 16 integration, Docker/Helm or real IdP ACL qualification.
- Existing GitHub Actions remain unchanged. HOLD / NO_GO unchanged.

### 2026-11-12 — bounded lab runner preflight hardening

- Added `--check-only` to `scripts/run_bounded_lab.py` for no-pytest checkout validation; moved report-path safety validation before subprocess invocation; refuse inherited database/replay environment variables even when empty.
- Added `tests/test_bounded_lab_runner.py`: synthetic-checkout preflight acceptance, missing source refusal, three inherited DB variable refusals, inside-checkout report refusal and outside-checkout dry-run. No external services or real database.
- These are committed test definitions, **not** proof of execution in a complete GAMMA checkout. GitHub Actions unchanged; HOLD / NO_GO unchanged.

### 2026-11-12 — ChatGPT lab preflight tests executed

- Executed `python -m pytest -q tests/test_bounded_lab_runner.py` in a disposable Python 3.13.5 / pytest 9.0.2 ChatGPT container using a manually reproduced two-file subset of the current PR source: **8 passed in 5.53s**.
- Details and strict provenance in `docs/CHATGPT-LAB-RUNNER-TEST-RESULT-20261112.md`. This is **not** a complete private repository checkout or a full application test run. PostgreSQL, frontend, Docker, Helm, IdP and real resource ACL remain unqualified.
- No changes to GitHub Actions, no merge/deployment/LIVE; HOLD / NO_GO remains.

### 2026-11-12 — lab runner execution contract, 13 passing local tests

- Added `tests/test_bounded_lab_execution_contract.py` with five mocked-subprocess cases for exit-code propagation, JSON report fidelity and refusal before test execution.
- Executed `python -m pytest -q tests/test_bounded_lab_runner.py tests/test_bounded_lab_execution_contract.py` in disposable ChatGPT Python 3.13.5 lab on manually reconstructed files: **13 passed in 5.55s**.
- Provenance and limitations in `docs/CHATGPT-LAB-EXECUTION-CONTRACT-20261112.md`. This does **not** establish full private checkout, exact-head CI, real PostgreSQL, IdP/ACL, Docker/Helm or production qualification.
- HOLD / NO_GO; no merge or deploy.

### 2026-11-12 — negative HTTP authorization before database access

- Added `tests/test_resource_list_http_denied_before_db.py` with **14 parametrized cases** (two real FastAPI GET list routes × seven invalid/missing signed-principal scenarios). A forbidden DB dependency spy asserts authentication failure precedes any DB session entry; responses must be 401 and `Cache-Control: no-store`.
- Included the new test file in the bounded ChatGPT lab allowlist (now 11 files). Tests are **committed but not yet executed** against a complete private checkout; no PostgreSQL/IdP/resource ACL qualification.
- GitHub Actions remain unchanged; HOLD / NO_GO, no merge/deploy/LIVE.

### 2026-11-12 — dotenv and pytest environment isolation

- Source audit found `app/settings.py` uses `SettingsConfigDict(env_file=".env")`; the bounded lab runner previously rejected only selected environment variables, not a checkout `.env` file.
- Updated `scripts/run_bounded_lab.py` to reject `.env` and inherited `PYTEST_ADDOPTS`, `PYTEST_PLUGINS`, `PYTHONPATH` (including empty values), before both `--check-only` and test subprocess execution.
- Added four synthetic preflight regression cases and one mocked-subprocess case. Adjusted existing runner test fixtures to scrub these inherited execution overrides. **Tests committed, not executed on a complete checkout**; previous 13-pass result applies only to the prior source version.
- GitHub Actions untouched; HOLD / NO_GO unchanged.

### 2026-11-12 — bounded lab timeout guard

- Added `LAB_TIMEOUT_SECONDS = 180` to the source-only lab runner. A timed-out pytest subprocess produces nonzero exit code `124` and explicit JSON `result: "timeout"`; normal pass/fail status is preserved.
- Added mocked-subprocess regression coverage for timeout reporting and timeout invocation; updated lab documentation.
- **Committed, not executed against a complete private checkout.** The previously observed 13-pass lab result does not apply to this latest source revision.
- HOLD / NO_GO; no GitHub Actions changes, merge, deployment or LIVE operations.

### 2026-11-12 — pytest plugin autoload boundary

- The bounded runner now sets `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` in its child process and explicitly loads `pytest_asyncio.plugin` with `-p`; the mocked subprocess contract asserts both properties.
- ChatGPT lab smoke check `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -p pytest_asyncio.plugin --version` succeeded with pytest 9.0.2. **This is a plugin-loading smoke check, not a GAMMA application test run.**
- GitHub Actions remain unchanged; exact-head full checkout tests and PostgreSQL/IdP qualification remain pending. HOLD / NO_GO.

### 2026-11-12 — quality review P0 fixes (source inspection)

- Corrected a literal backslash-n syntax defect in `app/schemas.py` (blocking `app.schemas` and API imports).
- Fixed `app/outbox_relay.py` import of nonexistent `app.db.session_factory` by using the existing lazy `get_session_factory()()`.
- Fixed `app/init_db.py` import of nonexistent `app.db.engine`; POC-only bootstrap now obtains the bound engine from the lazy sessionmaker, disposes it and clears the factory cache. Reviewed Alembic migrations remain mandatory for existing databases.
- Added `tests/test_quality_p0_imports.py` to parse all application Python files, check imports without DB initialization and assert lazy factory references.
- **These tests have been committed but not executed on the full repository checkout.** Prior CI runs did not provide test-step evidence. No PostgreSQL/IdP/ACL qualification; HOLD / NO_GO, no merge/deploy/LIVE.

### 2026-11-12 — P0 quality regressions promoted to bounded suite

- Added a fake-engine test for `app.init_db.main()` to assert the expected begin/run_sync/dispose/cache-clear sequence without connecting to a database.
- Added `tests/test_quality_p0_imports.py` to the fixed bounded lab allowlist, with updated lab documentation.
- **New tests not executed against a full checkout**. These are regression contracts, not proof of end-to-end startup or PostgreSQL qualification. HOLD / NO_GO remains.

### 2026-11-12 — CI syntax gate before pytest

- Reordered `.github/workflows/ci.yml` Python test job: `python -m compileall -q app tests scripts migrations deploy/scripts` now runs **before** the full `python -m pytest -q` suite.
- This makes malformed Python source (such as the earlier literal `\\n` in `app/schemas.py`) fail explicitly at the syntax gate instead of being obscured by test collection.
- This is a workflow change only: **no GitHub Actions step execution is yet evidenced at this commit**. Runner availability, full tests, PostgreSQL/IdP/ACL remain unqualified. HOLD / NO_GO.

### 2026-11-12 — first installable local MVP path (not yet runtime-qualified)

- API Dockerfile now includes `migrations/` and `alembic.ini`.
- Default Docker Compose now runs a one-shot `migrate` service with `alembic upgrade head` after PostgreSQL health, and gates API startup on successful completion.
- `scripts/smoke_local_mvp.py` provides read-only checks for loopback API health, frontend HTML and PostgreSQL Alembic head (`0002_gateway_replay`); `tests/test_local_mvp_install_contract.py` checks source wiring.
- README now describes the actual migration and smoke path rather than manual `app.init_db` initialization.
- **Not executed:** Docker is unavailable in the current workspace, and GitHub Actions failed before steps. No full Compose build, migration or smoke PASS is claimed. Frontend remains synthetic, not wired to authenticated API. No real IdP or tenant ACL qualification; HOLD / NO_GO for production/merge/LIVE.

### 2026-11-12 — No-VM local FastAPI smoke

- User has no test VM. Added `scripts/smoke_no_vm.py` (actual FastAPI TestClient, health, OpenAPI topology/evidence registration, unauthenticated tenant denial, no DB/network/containers) and `tests/test_no_vm_smoke.py`.
- README includes local venv installation and commands; the smoke refuses configured service/gateway secrets. This is a useful testable intermediate milestone, **not** proof of an installable end-to-end stack.
- Not executed against a full checkout in this session; CI runner pre-step failures persist. Production, external IdP, PostgreSQL, and frontend integration remain HOLD / NO_GO.


### 2026-11-12 — frontend synthetic demo boundary and CI runner blocker

- The synthetic-only frontend now limits Nginx and Vite proxying to exact `/api/v1/demo/correlation` and `/api/v1/demo/investigation` paths; other `/api/` requests are denied. Both proxies remove browser credentials and tenant/principal identity headers before forwarding.
- Nginx has bounded upstream connect/send/read timeouts; frontend fetches have 8-second abort signals. UI rejects authoritative, persisted, LIVE-authorized or structurally unexpected demo responses and clears stale correlation counters on error.
- `tests/test_frontend_demo_contract.py` covers the source contracts. A connector-side **static inspection** of 39 source invariants returned 39/39 matching; this is **not a test run, build or runtime security validation**.
- GitHub Actions workflows on recent commits fail within seconds with no assigned runner (`runner_id: 0`, `steps: []` for `test`, `frontend` and `gateway-replay-postgres`). Root cause **not established**; retrieve the GitHub job UI error annotation and check Actions permissions / billing only if indicated.
- Resume in order: (1) diagnose runner provisioning, (2) obtain successful `compileall`, full `pytest`, TypeScript/Vite build and disposable PostgreSQL migration/replay on **current HEAD**, (3) review tenant/auth and integration gates. No VM is available; no production qualification can be inferred.
- PR #1 stays draft, **HOLD / NO_GO**; no merge, deploy, or LIVE actions.

### 2026-11-13 — ITSM incident identifier revalidation

- Branch: `feat/observability-foundation`; draft PR #1.
- Commits: `18b9eb972978ca15532ee9fdb17f756ff4c6a87e` (runtime guard), `9950264d56e3cf908ca3695a2276a71fb676b7bd` (regression tests).
- Delivered: `plan_incident_sync()` now revalidates the mutable `incident_id` at the planning boundary, rejecting non-string values, blank/control-character values and identifiers longer than the schema's 128-character limit with a controlled `ValueError`. Added mutation regression cases plus a valid mutated identifier case.
- Validation: source and test changes are committed. **The tests have not been executed.** No workflow run was returned for the new HEAD; previous Actions failures had jobs with `steps: null` and no assigned runner. Do not claim pytest or CI passed.
- Scope/security: this hardens the preview contract only; no ITSM write, persistence, LIVE action or authorization capability is added. Issue #2 remains blocked on a real trusted actor→tenant ACL contract and upstream enforcement.
- Decision: HOLD / NO_GO; PR #1 remains draft. No merge, deployment or LIVE activation.
- Next: restore an executable CI runner and run the focused ITSM tests plus the full Python/frontend/PostgreSQL gates on the exact new HEAD; continue issue #2 only after the canonical services expose a verifiable tenant ACL contract.

### 2026-11-13 — ITSM mutable request structure hardening

- Branch: `feat/observability-foundation`; draft PR #1.
- Commits: `5562286d4998de2b48e6fdc01c01118eb907a605` and `0cab19e7dd7dcc63952faf1c55aa3adf3a0b1278` (request/matrix guards); `9690d36a783e93161eac3a67bc01f4a345a1f9d0` (regression tests).
- Delivered: the ITSM preview boundary now checks the request, incident and matrix model types before dereferencing; checks the matrix rule collection is a nine-item list of PriorityRule instances; and rejects invalid or non-string impact/urgency values before set operations. This prevents malformed post-validation mutations from surfacing as incidental Python attribute/type errors.
- Tests added for replaced nested models, malformed rule collections and invalid mutable priority levels. **Not executed**; source-level change only.
- CI: no exact-HEAD run has yet been evidenced. Previous failed jobs had no step records; downloadable job logs were unavailable (BlobNotFound). This does not establish the root cause.
- Security: preview-only; no ITSM writes, persistence, LIVE authorization or tenant ACL capability. Issue #2 remains blocked by the absent upstream actor→tenant authorization contract and unqualified Core/Evidence/Twin handlers.
- Decision: HOLD / NO_GO; PR #1 stays draft; no merge, deployment or LIVE activation.
- Next: diagnose GitHub Actions runner provisioning and run focused ITSM tests plus full Python/frontend/PostgreSQL gates on exact HEAD.

### 2026-11-13 — checkpoint after cross-repository ACL re-audit

- Re-read GAMMA issue #2 and its latest security findings, and checked the canonical `alimtalbi-ata/aiops` backlog. No verified gateway→actor→tenant membership/ACL contract is evidenced for GAMMA consumption; the upstream P0.1/P0.2 work remains a dependency, not a GAMMA-only implementation task.
- The prior finding remains: a shared service token plus caller-selected `X-Tenant-ID` authenticates a service caller but does not authorize that actor for the selected tenant. Existing Core/Evidence/Twin routes and the prototype GAMMA paths/schemas must not be assumed to provide resource-level tenant ACL.
- No speculative JWT/HMAC, issuer/audience, claim names, gateway namespace/pod selectors or route remapping added. Keep canonical reads and OpenSearch disabled for shared/staging/live.
- Current PR #1 HEAD before this documentation checkpoint: `b87c4d1ed0e44a87dc60a6591a93eceeed07d306`. The exact-HEAD workflow lookup returned no PR-triggered runs and no combined statuses; this is **not** CI PASS. The workflow-list connector is not available here, and historical missing-step jobs/logs do not prove why runners did not start.
- Refreshed `docs/PROJECT-STATUS.md` with the current security/CI decision. This handover entry records the cross-repository dependency.
- Decision remains **HOLD / NO_GO**: no merge, deployment, LIVE activation, tenant reads or ITSM writes.
- Next actionable dependency: the gateway/IdP and Core owners must provide a versioned, cryptographically verifiable caller identity and server-side actor→tenant/resource ACL contract, including issuer, audience, subject, membership/revocation semantics, key/JWKS or introspection lifecycle, and the actual read-only API routes/schemas. After that, implement and test authorization before data access, then run exact-HEAD CI and staging two-principal tests.

### 2026-11-13 — exact-HEAD CI runner failure confirmed through GitHub REST

- Current PR #1 HEAD: `594bd1caca76644ff6898bced9de2734612dce57`; latest Python checks run: [43415430933](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43415430933), event `pull_request`, conclusion `failure`, created 2026-11-13T11:14:12Z.
- Independently queried the run's jobs endpoint: `test` job `131851993708`, `frontend` job `131851994107`, and `gateway-replay-postgres` job `131851994327` all completed in 1–2 seconds, each with `runner_id: 0`, empty `runner_name`, and `steps: []`. No job acquired a runner or began a workflow step.
- Job-log endpoint previously returned `404 BlobNotFound`; no check-run annotation/root-cause detail was exposed by the available read interface. Therefore the evidence establishes **pre-runner failure**, not its cause. Do not guess billing, permissions, quota or GitHub incident.
- The workflow YAML itself declares ordinary `ubuntu-latest` hosted runners for Python, frontend, PostgreSQL replay and deployment contract. No speculative YAML change or retry can provision a missing hosted runner.
- The commit combined-status endpoint reports `pending` with zero status contexts; it does not override the failed Actions run.
- Actionable operator-side diagnostic remains in GitHub UI: inspect the run/job error annotation and repository/org Actions policy/hosted-runner availability; contact GitHub support if the annotation points to service-side provisioning. No repository-side configuration change is justified without that evidence.
- No application tests, frontend build, Compose/Docker smoke or PostgreSQL replay test executed. Keep **HOLD / NO_GO**, PR #1 Draft, no merge/deployment/LIVE.

### 2026-11-13 — CI recheck on documentation HEAD `c33248837b85f5ec1b73c718c61e64a846f4fc44`

- The documentation-only checkpoint itself triggered four runs on exact HEAD `c33248837b85f5ec1b73c718c61e64a846f4fc44`:
  - Python PR run [43415587282](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43415587282)
  - Python push run [43415570490](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43415570490)
  - Deployment-contract PR run [43415587656](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43415587656)
  - Deployment-contract push run [43415570396](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43415570396)
- Direct REST job records confirm **all 18 jobs** across these four runs failed before execution: `runner_id: 0`, empty runner name, zero steps; each started and completed within 1–2 seconds. This covers Python, frontend, disposable PostgreSQL replay, Compose, Helm, single-directory runtime, UI image and PostgreSQL non-root experiment.
- Therefore no compileall, pytest, frontend build, Docker/Compose, Helm or PostgreSQL step executed on this HEAD. The repeat across both `push` and `pull_request` events rules out a PR-only trigger issue, but does not identify the underlying hosted-runner provisioning cause.
- No speculative code/workflow edits or reruns made. Operator must inspect GitHub Actions UI annotations and repository/org runner policy/support. HOLD / NO_GO; no merge/deploy/LIVE.

### 2026-11-13 — upstream AIOPS authorization reuse review (read-only)

- Rechecked canonical repository `alimtalbi-ata/aiops` for work relevant to GAMMA issue #2. The best current reusable candidates remain Draft PRs, not approved/merged runtime contracts:
  - [AIOPS PR #631](https://github.com/alimtalbi-ata/aiops/pull/631), HEAD `2bd8cf4615f9fc185e74d43e91a0af5274f5a37e`: additive actor↔tenant grants, Run↔tenant bindings, bounded parameterized Runs reader, and disposable PostgreSQL isolation/revocation tests. It explicitly requires an already verified actor ID, has no trusted actor resolver or HTTP endpoint, and covers Runs only. Prior exact-HEAD CI was reported SUCCESS in AIOPS review docs, but that does not qualify an IdP or other resource families.
  - [AIOPS PR #668](https://github.com/alimtalbi-ata/aiops/pull/668), HEAD `fc970284bfcc991dbf146fe4fbec640d1ff2e14a`: documentation-only reuse plan; no authorization implementation.
  - [AIOPS PR #246](https://github.com/alimtalbi-ata/aiops/pull/246): OAuth2 introspection/exact-resource preflight candidate; deliberately no positive ALLOW because native GLPI actor rights and durable nonce/replay are unqualified; old stacked base.
  - [AIOPS PR #520](https://github.com/alimtalbi-ata/aiops/pull/520): signed GLPI xref/replay/read-only assembly primitives; its own contract states there is no production identity provider.
  - [AIOPS PRs #702/#704](https://github.com/alimtalbi-ata/aiops/pull/704): envelope schema and tenant-safe cache/cancellation acceptance specifications only; expressly NOT_IMPLEMENTED / NOT_EXECUTED.
- AIOPS PR #631 is not a drop-in authorization provider for GAMMA: its SQL only scopes Runs via explicit bindings/grants, actor identity is supplied by a caller that must already have verified it, and it does not authorize Incidents, Evidence, Twin graphs/aggregates or GLPI.
- Integration decision: do not copy or merge any AIOPS draft branch wholesale and do not change GAMMA upstream route mappings. AIOPS Core route/path and response contracts still need owner approval, server-side trusted principal resolution, tenant membership and per-resource filtering before serialization.
- This cycle was repository-source review only. No AIOPS/GAMMA application code, database, workflow, runtime, Debian, GLPI or LIVE state was changed.
- Next concrete dependency: AIOPS Core owner selects the IdP/gateway and approves a versioned principal + resource ACL contract; then implement authorization in canonical Core/Evidence/Twin, prove A→A and B→B positive plus A→B denial (including count/graph/evidence/error paths), and publish actual read-only route/schema contracts for GAMMA.
- GAMMA stays consumer-only, canonical reads disabled, OpenSearch disabled, PR #1 Draft, **HOLD / NO_GO**.

### 2026-11-13 — ChatGPT internal lab: Core read contract v1 proposal

- Added `docs/contracts/GAMMA-CORE-READ-CONTRACT-v1-PROPOSAL.md` on this draft branch. It defines the consumer contract only: logical families Incidents/Runs/Evidence/Twin; common `aiops2.read.v1` envelope; READY vs UNKNOWN/ERROR/BLOCKED semantics; bounded opaque cursor rules; source-side authorization-before-read; tenant-safe cache and cross-tenant test matrix.
- The proposal explicitly does **not** invent AIOPS route paths or claim AIOPS owner approval. Core/Gateway owners must publish exact routes, OpenAPI schemas, IdP contract, per-resource ACL, replay/key lifecycle and freshness policy before GAMMA implementation. GLPI remains separate.
- Preserved the current hard hold: `fetch_canonical()` must return 503 for every allowlisted canonical family; canonical/OpenSearch/GLPI flags remain disabled. No runtime code, upstream mapping, credentials or feature flags changed.
- Used the internal disposable ChatGPT Python lab for a narrowly reconstructed, no-network static check. Exact observed result: **3 passed in 0.07s** — existing canonical fail-closed AST shape, no-network/503 guard, and proposal required-token guard.
- **Limit:** this was a temporary reconstructed subset, not a full authenticated Git checkout. It is not execution of `scripts/run_bounded_lab.py`, not the repository's 12-file allowlist, not real FastAPI/PostgreSQL/IdP/HTTP integration, and not exact-HEAD GitHub CI. Do not promote this result as full application qualification.
- No PostgreSQL, network, Docker, Debian, GLPI, upstream API or LIVE resources accessed. PR #1 remains Draft and **HOLD / NO_GO**.

### 2026-11-13 — disposable PostgreSQL-backed HTTP tenant-isolation test added

- Added `tests/test_resource_list_http_postgres.py`: exercises the real FastAPI list routes for ServiceBinding and Evidence using actual async PostgreSQL sessions. It seeds two tenants, signs distinct request-bound gateway assertions, deliberately forges contradictory browser tenant/actor/role headers, and checks responses are isolated by the verified principal; Evidence is also scoped by incident.
- Safety guards: explicit `GAMMA_TENANT_TEST_DATABASE_URL`, PostgreSQL+asyncpg only, loopback host only, database name `*_tenant_test`, explicit `GAMMA_TENANT_TEST_ALLOW_WRITE=I_UNDERSTAND_DISPOSABLE_DB`, independently verified connected database identity, exact Alembic revision `0002_gateway_replay`, required tables present and empty before seeding, SQLAlchemy NullPool, cleanup restricted to generated row IDs. The test does not create/drop schema or truncate tables.
- Added `docs/CHATGPT-LAB-POSTGRES-TENANT-HTTP-TEST-20261113.md` with provisioning and invocation instructions. Nine parameterized cases are expected when an explicitly provisioned disposable PostgreSQL database is supplied.
- **Execution status: NOT EXECUTED.** No PostgreSQL server or authenticated full repository checkout was available in this ChatGPT lab; no DB was created/contacted. Missing URL causes pytest skip; unsafe URLs fail. Do not report these tests as passing.
- Existing in-memory SQL spy HTTP tests remain the only currently recorded resource-list HTTP isolation evidence. The new test, once run, will add real PostgreSQL evidence for these two GAMMA routes only; it does not qualify IdP, upstream Core/Evidence/Twin ACL, RLS, replay, GLPI, aggregates/graphs or LIVE.
- No runtime code, migrations, gateway behavior, route mapping, feature flag or production resource changed. Canonical reads remain unconditional 503. PR #1 Draft; **HOLD / NO_GO**.

### 2026-11-13 — bounded ChatGPT lab safety check + exact-HEAD CI recheck

- In the available disposable ChatGPT Python 3.13.5 environment, ran five isolated SQLAlchemy URL-guard assertions copied from the new PostgreSQL test contract: one loopback `*_tenant_test` URL accepted; production DB name, staging DB name, SQLite driver and remote host rejected. Observed: **5 assertions passed**. No PostgreSQL driver/server was installed and no database connection was attempted.
- This is only URL-guard unit evidence. The new `tests/test_resource_list_http_postgres.py` has **not** been executed against PostgreSQL; it requires an operator-provisioned, empty, loopback disposable DB at Alembic revision `0002_gateway_replay` and explicit write acknowledgement.
- Current PR #1 exact HEAD is `053b40d49c0e59914797b05925a79cd3af08563f`. Four latest push/PR workflow runs: Python [43416548953](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43416548953), deployment PR [43416548656](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43416548656), deployment push [43416541682](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43416541682), Python push [43416541671](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43416541671).
- Direct jobs API: all 18 jobs show `runner_id: 0`, empty runner name and zero steps. No Python, frontend, replay PostgreSQL, Compose, Helm or runtime smoke test ran. This remains a pre-runner failure; root cause not established.
- PR #1 remains open Draft, unmerged. No application runtime, migrations, database, gateway, upstream route, GLPI or LIVE state changed. Canonical reads remain hard 503. **HOLD / NO_GO**.

### 2026-11-13 — CI retry confirms runner bootstrap failure

- Retried failed jobs on exact HEAD `e5197c194d760308ca98d9f755ee12382a9b4b9e`: Python checks run `43416611552` and Deployment contract run `43416611515` (attempt 2).
- Both retry attempts terminated in approximately 2 seconds. All 9 jobs report `runner_id: 0`, empty `runner_name`, zero steps, and no job logs are available (GitHub job-log endpoint returns BlobNotFound). Thus no checkout, dependency installation, pytest, PostgreSQL service, Docker, Helm or runtime step started.
- The repeat rules out a one-off transient runner allocation delay but does not identify the account/repository-level root cause. Workflow YAML declares `ubuntu-latest`; repository Actions permissions/runners configuration could not be inspected through the available GitHub connector. An authorized repository administrator must inspect Actions settings/billing/runner availability and check-suite annotations.
- No code changes made to CI workflows to mask this infrastructure failure. No test result has been inferred from the red check state.
- Exact HEAD remains `e5197c194d760308ca98d9f755ee12382a9b4b9e`; PR #1 open Draft/unmerged. Canonical reads remain hard 503. **HOLD / NO_GO**.

### 2026-11-13 — ChatGPT local lab first, no GitHub Actions reruns

- User directed local ChatGPT lab as primary test environment. No GitHub Actions rerun or workflow modification was requested or performed in this cycle.
- Corrected `tests/test_resource_list_http_postgres.py`: signed request helpers now use independent actor `sub` values for tenant A and tenant B (previously both used the same actor ID), and a new non-regression test verifies distinct subjects, tenants, JTIs, and identical bound GET path/method. Commit `a31cb0177c85157d1f35d2f8b0451fb3fcf7a33b`.
- Ran seven isolated Python/pytest assertions in the disposable ChatGPT environment (0.18s): reconstructed HMAC principal signing/verification and actor isolation plus six PostgreSQL URL allow/deny cases. **7 passed**.
- **Evidence limitation:** the local module was reconstructed from the relevant helper, not imported from a complete authenticated repository checkout. This is not an execution of the committed repository test module, nor FastAPI HTTP, asyncpg/PostgreSQL, migration or full CI qualification. PostgreSQL integration tests remain **NOT EXECUTED**.
- No PostgreSQL server, Docker, external network, gateway, GLPI or LIVE resources accessed. Canonical reads remain hard-disabled; PR #1 stays Draft. **HOLD / NO_GO**.

### 2026-11-13 — ChatGPT lab-first follow-up, no Actions invocation

- User requested that the disposable ChatGPT lab take priority over blocked GitHub Actions. No Actions runs, retries or CI edits were initiated.
- Re-ran the existing local reconstructed principal/URL test harness in `/mnt/data/gamma_lab/test_principal_contract.py`: `python -m pytest -q test_principal_contract.py` => **7 passed in 0.19s**. This is local harness evidence only, not a full GitHub checkout or a run of repository `tests/test_resource_list_http_postgres.py`.
- Updated the PostgreSQL HTTP test documentation to reflect the prior code correction: two **distinct** actor subjects and **10** declared test cases (4 HTTP cases requiring PostgreSQL, 4 unsafe-URL cases, 1 safe-URL case, 1 actor-distinctness case). The HTTP/PostgreSQL tests are still **NOT EXECUTED**.
- The environment has pytest, FastAPI, SQLAlchemy and Alembic, but no asyncpg or PostgreSQL server executable; network access to github.com is unavailable from the container. Do not treat this as full source qualification.
- No database, network, production resource, gateway, GLPI, feature flag, upstream route or LIVE access changed. PR #1 remains Draft, canonical reads hard-disabled. **HOLD / NO_GO**.

### 2026-11-13 — ChatGPT lab: PostgreSQL query-host override guard

- Identified a safety gap in `tests/test_resource_list_http_postgres.py`: `sqlalchemy.engine.make_url(...).host` can report `localhost` while `parsed.query` contains `host=db.internal` or `host=/var/run/postgresql`. Such query parameters may alter the actual asyncpg connection target despite a loopback-looking authority.
- Added a fail-closed `if parsed.query: pytest.fail(...)` guard before accepting the URL; added three regression cases for remote host override, Unix-socket override, and unexpected SSL query configuration. Commit `67d202153cb97f9c5ff66e99a86799514875def2`.
- Reproduced the guard in a standalone local ChatGPT lab test file `/mnt/data/gamma_lab/test_pg_url_query_guard.py` using the actual installed SQLAlchemy URL parser: **10 passed in 0.16s** (7 denied URLs + 3 allowed loopback variants). This is a faithful isolated reproduction of the helper, **not** a run of the repository module or a PostgreSQL connection.
- Updated test documentation: total declared repository test cases now **13** (4 HTTP requiring PostgreSQL + 7 unsafe URL + 1 safe URL + 1 distinct-actor).
- No GitHub Actions invocation, external database, network, migration, runtime application, gateway or LIVE change. PostgreSQL-backed HTTP tenant isolation remains **NOT EXECUTED**. PR Draft; canonical reads hard-disabled; **HOLD / NO_GO**.

### 2026-11-13 — ChatGPT lab PostgreSQL connected-server preflight

- Extended `tests/test_resource_list_http_postgres.py` to verify, before any test-data insertion, that PostgreSQL's **actual** `inet_server_addr()` is loopback TCP (no remote server or Unix socket), the current role is **not** a superuser, and `server_version_num` is PostgreSQL 16. This adds a second independent defense beyond the already strict URL guard and connected database-name check. Commit `67494922e85a80c40670bd8eb4c22fd7e3beff86`.
- In the disposable ChatGPT Python lab, ran `python -m pytest -q test_pg_server_identity.py test_pg_url_query_guard.py test_principal_contract.py` => **27 passed in 0.18s**. The 10 new cases cover allowed IPv4/IPv6 loopback, remote/socket rejection, superuser/unverified role rejection and unsupported PostgreSQL version rejection.
- **Evidence boundary:** these tests exercise isolated reconstructed predicates, not an authentic repository checkout, actual FastAPI route, real PostgreSQL connection, Alembic migration or end-to-end actor→tenant authorization. The repository PostgreSQL HTTP tests remain **NOT EXECUTED**. The local lab did not contact a database or GitHub Actions.
- No runtime application, migration, gateway, canonical adapter, production resource or LIVE state changed. PR #1 remains Draft, canonical reads hard 503, **HOLD / NO_GO**.

### 2026-11-13 — Local lab-first syntax repair on committed PostgreSQL test

- Inspected the exact repository file `tests/test_resource_list_http_postgres.py` through the connected source interface and found a **real syntax defect**: the earlier URL-query guard had been committed with literal `\\n` sequences inside Python source. This made the repository test module invalid, despite isolated reconstructed helper tests passing. Corrected it on the Draft PR branch, commit `1f41686d7c96de0b1efb6f94c40e065e63edc97e`.
- Re-fetched the exact updated file and verified that the malformed literal sequence is absent and that the proper multi-line `if parsed.query:` fail-closed guard and connected-server checks are present.
- Re-ran the existing local reconstructed ChatGPT harness in `/mnt/data/gamma_lab`: `python -m pytest -q` => **27 passed in 0.19s**. **Important:** this harness is not the actual repository pytest module; it would not have detected the malformed source. The syntax repair was confirmed by source inspection, not a complete checkout compilation.
- No GitHub Actions reruns, external PostgreSQL connection, runtime changes, upstream access, merge or LIVE actions. PR #1 remains Draft; **HOLD / NO_GO**.

### 2026-11-13 — ChatGPT lab: prevent vacuous multi-tenant test passes

- Reviewed actual committed `tests/test_resource_list_http_postgres.py` via the GitHub connector. The `test_foreign_rows_and_foreign_incident_are_not_serialized` case used `all(... for ... in values)` and negative-only assertions: **an empty HTTP 200 list would pass**, without demonstrating a legitimate tenant-owned row was returned.
- Replaced the negative-only check with `assert values == expected`, where the expected positive row is tenant A's service binding or evidence for the requested incident; retained explicit forbidden foreign/other-incident checks. Commit `c447773d828fa0787f66775cd7b7216b815e4b29`.
- Ran the disposable ChatGPT local harness `python -m pytest -q` in `/mnt/data/gamma_lab`: **34 passed in 0.20s**, including 7 isolated positive/negative assertion scenarios. These are **reconstructed local unit checks**, not a checkout or execution of repository HTTP/PostgreSQL tests. PostgreSQL-backed tests remain **NOT EXECUTED**.
- No GitHub Actions invocation, database connection, runtime changes, upstream read, merge or LIVE action. PR #1 stays Draft. **HOLD / NO_GO**.

### 2026-11-13 — Source parsing guard added, lab-first

- Added `tests/test_python_source_parse_contract.py` on Draft branch (commit `b8961c7083401f021cdd4dfd83539fb2516f88d8`). It parses all Python sources under `app/`, `tests/`, `migrations/`, and `scripts/` with `ast.parse` without imports, DB access or network, and statically requires a positive exact-row assertion in the PostgreSQL tenant isolation test. This is a regression guard against the literal-`\\n` syntax defect previously discovered.
- Re-ran the **existing local reconstructed harness** `python -m pytest -q /mnt/data/gamma_lab`: **34 passed in 0.29s**. Independently parsed the four Python files in that local harness successfully.
- **Do not conflate evidence:** the newly committed source parsing test has not run against a full authenticated repository checkout. Local container cannot resolve github.com, and the GitHub connector does not mount a checkout into the container. Full repository syntax/pytest/HTTP/PostgreSQL qualification remains outstanding.
- No GitHub Actions reruns, production or disposable DB access, merge, deployment, upstream read, canonical enablement or LIVE action. **HOLD / NO_GO**.

### 2026-11-13 — Python -O safe disposable PostgreSQL preflight

- Identified that the pre-write disposable PostgreSQL identity/emptiness checks in `tests/test_resource_list_http_postgres.py` used bare `assert`, which Python removes under `-O`. Replaced them with explicit `if ...: pytest.fail(...)` checks for connected database suffix, actual loopback TCP server, non-superuser, PostgreSQL 16, exact Alembic revision, required tables, and empty tenant tables. Commit `856a804dd339f65c47ae0b61c38f6159c9829143`.
- Added static AST regression test `test_disposable_postgres_preflight_never_uses_optimizable_assertions` in `tests/test_python_source_parse_contract.py`; requires fail-closed checks and prohibits bare `assert` in the connected-server preflight. Commit `cb1d92449d8fb2eee56d4624c8298e67284081a6`.
- Executed `python -m pytest -q /mnt/data/gamma_lab/test_preflight_optimization_contract.py` in ChatGPT lab: **2 passed in 0.04s**, covering six denied preflight conditions under both Python optimize levels 0 and 2. This local test is a **reconstructed preflight pattern**, not the authentic repository module or a real PostgreSQL session.
- No GitHub Actions rerun, DB connection, migration, production write, runtime change, merge or LIVE access. PR Draft, canonical reads hard disabled, **HOLD / NO_GO**.

### 2026-11-13 — Second real-source syntax repair (URL cases)

- Re-inspected the **full authentic GitHub source text** of `tests/test_resource_list_http_postgres.py` and discovered **three additional literal `\\n` sequences** in the `@pytest.mark.parametrize("url", ...)` cases. The earlier repair had fixed only the guard block; the module still could not parse. Removed all three remaining sequences in commit `52c46f0471dd824aad28bee7fed1f9cdb8cde3fc`.
- Re-fetched the updated source and verified those literal escaped-newline sequences are absent and the three added unsafe URL cases remain present.
- **Evidence boundary:** this was an authentic repository source inspection and committed repair, not a successful full checkout `ast.parse` or execution of the repository test module. The newly committed `test_python_source_parse_contract.py` is designed to catch exactly this class of defect once executable against a complete checkout.
- No GitHub Actions invocation, DB connection, migrations, upstream calls, merge, deployment or LIVE changes. PR #1 remains Draft; **HOLD / NO_GO**.

### 2026-11-13 — In-memory HTTP SQL-spy tenant fixture fidelity

- Corrected `tests/test_resource_list_http_tenant_isolation.py`: the tenant A/B request pair previously used the same signed `sub` and `jti`, and the two binding objects shared one UUID. It now uses tenant-distinct actor subjects, unique assertion IDs and unique service-binding IDs. Commit `8dcd418585071b2d4c16de500035bb7fd8ad69d7`.
- Executed the available reconstructed ChatGPT local harness `cd /mnt/data/gamma_lab && python -m pytest -q`: **36 passed in 0.24s**. These are reconstructed unit tests only; the modified authentic repository HTTP test has **not** been executed in the container.
- No GitHub Actions, database connection, migration, runtime change, merge, deployment or LIVE action. Draft PR #1 and **HOLD / NO_GO** remain.

### 2026-11-13 — Authentic source guard executed in partial ChatGPT checkout

- Retrieved the **actual** `tests/test_python_source_parse_contract.py` content from GitHub and materialized it at `/mnt/data/gamma_authentic_subset/tests/test_python_source_parse_contract.py` in the internal ChatGPT container. Executed its original `test_all_python_sources_parse_without_imports` on this partial local tree and two local mutation probes (valid and intentionally malformed Python files): `python -m pytest -q test_source_parser_mutation.py tests/test_python_source_parse_contract.py::test_all_python_sources_parse_without_imports` => **3 passed in 0.04s**.
- Promoted the two mutation scenarios into the authentic repository source-guard test module (commit `461a7d0fd6f8e60f167a358663053da83cb484ff`). They validate that the guard catches a literal backslash-n source defect and accepts valid source. The newly committed mutation test additions have not yet been run from the updated GitHub file in the lab.
- **Scope:** this is the first execution of a genuine copied GAMMA test function in a partial local tree; **not** full-repository AST validation, FastAPI HTTP execution, real PostgreSQL, IdP or upstream ACL. No GitHub Actions invocation or LIVE/merge/deploy. **HOLD / NO_GO**.

### 2026-11-13 — Authentic source-guard tests run in ChatGPT subset

- Materialized the exact two source-parser mutation tests previously committed to `tests/test_python_source_parse_contract.py` in the partial ChatGPT lab checkout and executed them: **2 passed**. Added a third mutation scenario that explicitly refuses an empty source tree (commit `9dca3c290bd8b1b320cc6fcf880e5ff7b6703106`).
- Ran the four selected **authentic source-guard test functions** in `/mnt/data/gamma_authentic_subset`: `python -m pytest -q tests/test_python_source_parse_contract.py -k 'source_parser or all_python_sources_parse'` => **4 passed, 2 deselected in 0.04s**. The tested functions include the source scan on the partial tree, invalid-source rejection, valid-source acceptance and missing-source rejection.
- **Scope limitation:** partial checkout contains only the source-guard test module and local helper files, not all GAMMA Python sources. The two deselected AST contract tests require authentic PostgreSQL test source not yet present locally. This is not a full-repository syntax scan, FastAPI execution, PostgreSQL validation, IdP or upstream ACL qualification.
- No GitHub Actions, DB connection, runtime change, merge, deploy or LIVE operation. PR #1 Draft; **HOLD / NO_GO**.

### 2026-11-13 — Authentic tenant-scope code and tests in ChatGPT lab

- Retrieved actual GitHub source `app/reused/tenant_scope.py` and its actual test module `tests/test_tenant_scope_guard.py`, materialized both under `/mnt/data/gamma_authentic_subset/` without changing their logic.
- Executed `cd /mnt/data/gamma_authentic_subset && python -m pytest -q tests/test_tenant_scope_guard.py tests/test_python_source_parse_contract.py -k 'not postgres'`: **23 passed, 2 deselected in 0.07s**. This includes real `reject_unqualified_tenant_scope` implementation and its tests, plus source-guard tests. No DB, network or GitHub Actions involved.
- Scope remains **partial checkout**: PostgreSQL AST contract tests deselected; no complete GAMMA source tree, FastAPI app tests, real PostgreSQL, gateway/IdP or source-side ACL qualification. No production action, merge, deployment or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Genuine tenant-scope tuple bypass found and fixed

- Ran the actual `reject_unqualified_tenant_scope` from `app/reused/tenant_scope.py` in the internal ChatGPT lab against two untrusted nested tuple payloads containing `tenant_id`: **both were accepted before the fix**. The scanner previously descended into `dict` and `list` but not `tuple`.
- Updated the scanner to recurse into both lists and tuples (commit `eb0f38d759e5b8b04653bb15e9c449ee1fd83d55`). Added three malicious tuple nesting cases and one benign tuple case to the actual `tests/test_tenant_scope_guard.py` (commit `f543cec0a95904d754b95fb6c61c2c7fae7f80df`).
- Applied the exact minimal source change and test additions to the existing partial ChatGPT lab copy and executed `python -m pytest -q tests/test_tenant_scope_guard.py tests/test_python_source_parse_contract.py -k 'not postgres'`: **27 passed, 2 deselected in 0.06s**.
- This is a diagnostic metadata guard, **not** actor→tenant or source-side resource authorization. Full checkout/HTTP/PostgreSQL/IdP/ACL/replay qualifications outstanding. No GitHub Actions, DB, merge, deployment or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Genuine redaction suffix leak found and fixed

- Materialized actual `app/reused/redaction.py` and `tests/test_redaction.py` from the GitHub branch into the partial ChatGPT lab checkout. The **13 original tests passed**.
- Discovered an actual leak for quoted credential values containing spaces: `password="alpha beta gamma"` returned `password="[REDACTED] beta gamma"`, exposing the suffix. JSON quoted `api_key` exhibited the same issue.
- Updated the named-credential regex to consume an entire quoted value (single or double quotes) rather than only the first whitespace-delimited token; commit `3f12c33bcc1a6d7aefeb5b2f3d9cd6c81268977f`. Added a regression covering password, JSON api_key and client_secret with spaces; commit `93eccbd5623559220269ff96f11bc921a1f41330`.
- Applied the exact code and test edits in ChatGPT lab: `python -m pytest -q tests/test_redaction.py` => **14 passed in 0.05s**. This validates the real module and test file in a partial checkout, **not** complete repository/HTTP/PostgreSQL/IdP/ACL qualifications.
- No GitHub Actions, DB, merge, deployment or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Additional genuine diagnostic secret leak repaired

- Ran actual `app/reused/redaction.py` in partial ChatGPT lab. Confirmed **unclosed quoted credentials** (e.g. `password="alpha beta`) passed through unredacted, including multiline input; an **escaped quote** inside a credential left its suffix visible.
- Updated the named-secret regex to recognize escaped characters in closed quoted values and conservatively redact the remaining text for unclosed quoted values. Code commit `7073fc75c2e39ae625a814bb18e52c7ad14431e9`; regression tests commit `0ea3f57931ba5cf0ebd9e4274af11eda7650f9ea`.
- Applied matching code and tests to the local authentic partial checkout. `python -m pytest -q tests/test_redaction.py` => **16 passed in 0.06s**. Three additional adversarial examples were separately checked. This is module-level evidence only, not end-to-end logging, HTTP, PostgreSQL, IdP or resource ACL qualification.
- No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Authentic canonical upstream HOLD tests in ChatGPT lab

- Retrieved the actual GitHub source of `app/settings.py`, `app/reused/upstream.py` and `tests/test_upstream.py` from Draft branch and materialized them in `/mnt/data/gamma_authentic_subset/` alongside previously materialized authentic tenant-scope, redaction and source-guard modules.
- Executed `cd /mnt/data/gamma_authentic_subset && python -m pytest -q tests/test_upstream.py tests/test_tenant_scope_guard.py tests/test_redaction.py`: **55 passed in 0.37s**.
- Executed the expanded local authentic subset `python -m pytest -q tests/test_upstream.py tests/test_tenant_scope_guard.py tests/test_redaction.py tests/test_python_source_parse_contract.py -k 'not postgres'`: **59 passed, 2 deselected in 0.35s**.
- Canonical tests verify 503 for core/evidence/twin even when legacy enable flag and token are set, 404 for unknown resources, and no `httpx.AsyncClient` invocation; origin validator tests reject unsafe URLs. No actual upstream network requests made.
- Evidence applies to this **partial** locally materialized authentic source subset, not a full repository checkout or real HTTP/PostgreSQL/IdP/source-side ACL qualification. No GitHub Actions, DB connection, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Genuine gateway verifier + isolated FastAPI HTTP boundary in ChatGPT lab

- Materialized the actual `app/security.py`, `app/settings.py`, and `tests/test_gateway_auth_extra.py` into `/mnt/data/gamma_security_lab/` from the GitHub branch. Executed the **16 original signed assertion tests** successfully.
- Built a minimal local FastAPI `TestClient` harness that imports the **real `internal_principal` dependency** and tests two HTTP behaviors: a forged `X-Tenant-ID` cannot override the tenant in a valid signed gateway assertion, and `X-Tenant-ID` plus service key without gateway assertion returns 401.
- `cd /mnt/data/gamma_security_lab && python -m pytest -q tests/test_gateway_auth_extra.py tests/test_http_gateway_probe.py` => **18 passed in 0.32s**. Promoted the two new tests to the actual repository's existing isolated FastAPI dependency suite `tests/test_gateway_dependency_http_isolated.py` (commit `657bd8b4bda6222b17236ccc89c63433f0ab7169`). The entire original HTTP suite has not yet been materialized/run locally.
- These tests validate the exact gateway verifier and dependency against a **local synthetic probe route**, not real GAMMA business routes, external IdP, actor membership, source-side resource ACL, PostgreSQL or replay. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Entire authentic isolated FastAPI gateway HTTP suite executed

- Retrieved the complete actual `tests/test_gateway_dependency_http_isolated.py` from Draft branch, including the two recently promoted tenant-header regression tests, and materialized it under `/mnt/data/gamma_security_lab/tests/`. The existing lab already contained exact `app/security.py`, `app/settings.py` and `tests/test_gateway_auth_extra.py` fetched from GitHub.
- Executed `cd /mnt/data/gamma_security_lab && python -m pytest -q tests/test_gateway_dependency_http_isolated.py tests/test_gateway_auth_extra.py`: **37 passed in 0.49s**. This includes the complete authentic isolated HTTP suite, not merely a reconstructed probe.
- Verifies real `internal_principal` dependency with FastAPI TestClient: rejects service-key-only and untrusted identity headers, wrong keys, invalid/expired/method/path-mismatched assertions, duplicate JSON claims, noncanonical base64url and tampered signatures; signed tenant remains authoritative over forged `X-Tenant-ID`.
- Scope: isolated synthetic `/api/v1/probe` endpoint with real security dependency, **not** all GAMMA business routes or real IdP/gateway/actor→tenant→resource ACL. No PostgreSQL or upstream HTTP qualification. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Authentic canonical HOLD static guard and mutation probes

- Retrieved and materialized the exact `tests/test_canonical_acl_hard_hold_static.py` in `/mnt/data/gamma_authentic_subset/` alongside authentic upstream, tenant-scope and redaction sources and tests.
- Executed `python -m pytest -q tests/test_canonical_acl_hard_hold_static.py tests/test_upstream.py tests/test_tenant_scope_guard.py tests/test_redaction.py`: **56 passed in 0.34s**.
- Exercised the actual static HOLD guard against two local mutated copies of `app/reused/upstream.py`: (1) replacing unconditional 503 with a positive return, and (2) inserting network I/O before the 503. Both were rejected; targeted run **3 passed in 0.03s** (the original guard and two local mutation tests).
- Promoted both mutation checks to authentic `tests/test_canonical_acl_hard_hold_static.py`, commit `854ed77d41112e6c9679cab327acf0424d04491d`. Local mutation checks used a separate helper file with equivalent logic; newly committed exact test file has not been rerun after promotion.
- Static source and local subset only: not real business-route HTTP, upstream source ACL, PostgreSQL, IdP or replay. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Executed promoted canonical HOLD mutation tests; fixed false evidence

- Reproduced the **exact two promoted mutation tests** in the ChatGPT lab with authentic `app/reused/upstream.py` and the actual static guard. Initial run: **1 failed, 2 passed** in the targeted suite: the pre-denial network mutation inserted literal `\\n`, causing `SyntaxError` rather than exercising the intended AST denial assertion.
- Fixed the test string to inject a real newline, commit `5abc8ffa34b06d43006f9120920042b2b3f75d24`; reran `python -m pytest -q tests/test_canonical_acl_hard_hold_static.py tests/test_upstream.py tests/test_tenant_scope_guard.py tests/test_redaction.py`: **58 passed in 0.36s** in the partial authentic source lab.
- This repairs test validity; no new runtime authorization was established. The guard still enforces static unconditional denial of canonical reads. No full checkout, business-route HTTP, PostgreSQL, IdP or upstream resource ACL validation. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Exact tenant isolation assertion static contract repaired

- Retrieved genuine `tests/test_python_source_parse_contract.py`. Discovered that its AST guard accepted a bare `values == expected` expression, without requiring a runtime `assert`; such a no-op comparison could mask a vacuous/absent positive tenant-row check.
- Changed the guard to require an actual `ast.Assert` with exactly `values == expected`, and repaired the syntax mutation fixture to use genuine newline characters instead of literal backslash-n, commit `c1e2c0341fd78c4dd654f055e8fa09a7b2d5d27c`.
- Promoted two authentic mutation tests: a no-op comparison must be rejected, an executable assertion accepted, commit `6e996499f7bfcdc9fad357c55b36fb03eced191f`.
- Applied the same source and tests in the partial ChatGPT lab: `python -m pytest -q tests/test_python_source_parse_contract.py -k 'source_parser or all_python_sources_parse or exact_row_guard'` => **6 passed, 2 deselected in 0.05s**. The deselected AST tests still require the actual PostgreSQL test source to be materialized. This is static/test integrity evidence, not a real PostgreSQL tenant isolation run.
- No GitHub Actions, DB, merge, deployment or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — PostgreSQL pre-write guard strengthened against Python -O bypass

- Inspected the exact `tests/test_resource_list_http_postgres.py` on the Draft branch (12,120 characters): `tenant_postgres.prepare()` performs disposable DB identity, loopback TCP, non-superuser, PostgreSQL 16, Alembic head, table presence and emptiness checks before inserts. No PostgreSQL connection was made.
- Discovered a blind spot in `tests/test_python_source_parse_contract.py`: the `ast.Assert` ban covered only the first `async with engine.connect()` block, allowing optimizable assertions elsewhere in `prepare()` before writes. Strengthened the ban to all AST nodes in `prepare()`, commit `4b6cb977aa4dbb92c2d3fbaf91f3896519d9ec3b`.
- In the internal ChatGPT lab, executed three AST mutation checks against a representative `prepare()` fixture: benign fixture accepted, an assertion inserted between connection and session blocks rejected, and an assertion inside the session block rejected; **3 passed in 0.03s**. These were representative AST tests, **not** the complete authentic PostgreSQL source or the newly committed regression test.
- Added a regression mutation test to the actual repository that injects a pre-write assertion into the genuine PostgreSQL source and requires the static guard to reject it, commit `bdd0831e37871fa73f291cbbe770e932414cda13`. This exact committed test has not yet run locally; the complete source is still not materialized in the ChatGPT lab.
- No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Full authentic PostgreSQL test source parsed; both excluded AST checks now pass

- Materialized the complete source of `tests/test_resource_list_http_postgres.py` (12,120 characters fetched from GitHub) under `/mnt/data/gamma_authentic_subset/tests/`. This was a manual transcription of the retrieved full file, **not a byte-for-byte verified Git checkout**.
- `python -m py_compile tests/test_resource_list_http_postgres.py` succeeded **without importing app code or connecting to PostgreSQL**.
- Updated the partial local copy of `tests/test_python_source_parse_contract.py` with the committed expanded `prepare()` AST guard and its new pre-write mutation regression. `python -m pytest -q tests/test_python_source_parse_contract.py`: **9 passed in 0.06s**, including both formerly deselected PostgreSQL AST checks and the new mutation test.
- Full local authentic-module subset: `python -m pytest -q tests/test_python_source_parse_contract.py tests/test_tenant_scope_guard.py tests/test_redaction.py tests/test_upstream.py tests/test_canonical_acl_hard_hold_static.py`: **67 passed in 0.30s**. The PostgreSQL HTTP integration tests themselves were **not run**: no PostgreSQL 16, asyncpg or disposable DB was provisioned.
- This is AST/syntax/static source evidence, **not** real actor→tenant→resource authorization, database isolation, actual GAMMA route HTTP, IdP or upstream ACL qualification. No GitHub Actions, DB connection, merge, deployment or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Signed gateway subject unpaired-surrogate rejection

- Tested exact GitHub `app/security.py` in the ChatGPT internal lab: a correctly HMAC-signed assertion with `sub="user:\\ud800"` was **accepted**, producing a `Principal.subject` that fails ordinary UTF-8 encoding with `UnicodeEncodeError`.
- Added a fail-closed subject validation check rejecting Unicode surrogate code points U+D800–U+DFFF, commit `3e40a6e51be2e568f8c8391439f27039f1fb4fbb`. Added two signed regression cases (U+D800 and U+DFFF) to `tests/test_gateway_auth_extra.py`, commit `2b011cacbc7783e82861f7d42ab3012c4f354e2b`.
- Local lab executed the corresponding updated authentic security module and regression tests: `python -m pytest -q tests/test_gateway_auth_extra.py tests/test_http_gateway_probe.py` => **20 passed in 0.32s**. The probe file is local and is not a complete GAMMA route integration suite.
- This prevents a malformed signed subject from entering downstream code; it does **not** establish actor→tenant membership, upstream resource ACL, PostgreSQL isolation, replay qualification or a real IdP/gateway. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Full isolated gateway suite with Unicode regression at HTTP boundary

- Ran actual copied `app/security.py` and `app/settings.py` with `tests/test_gateway_auth_extra.py`, complete `tests/test_gateway_dependency_http_isolated.py` and local `tests/test_http_gateway_probe.py`: **41 passed in 0.36s** before new tests.
- Added two FastAPI TestClient HTTP dependency regressions for HMAC-signed subjects containing U+D800/U+DFFF, requiring HTTP 401. Ran the combined local suite: **43 passed in 0.40s**.
- Promoted these two HTTP regression cases to the authentic `tests/test_gateway_dependency_http_isolated.py`, commit `533e9fa574fffaea1bd0aeddabc0de1884d8121a`.
- Scope: isolated FastAPI probe with genuine security dependency and local test files, **not** real GAMMA business routes, real gateway/IdP, upstream actor→tenant→resource ACL, PostgreSQL or replay. No GitHub Actions, database connection, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Actual route inventory drift found; public demos explicitly guarded

- Inspected the complete actual `app/main.py` (346 lines) against `tests/test_route_security_static.py`. The static test's exact expected route inventory omitted two existing public, synthetic-only GET routes: `/api/v1/demo/correlation` and `/api/v1/demo/investigation`. Therefore the old inventory check would fail on the actual app source.
- Updated the inventory and explicit public allowlist to include only those two demos and `/api/v1/health/live`, commit `b412922eaebcfba9837c7658b6129e53f42fe28f`. All other routes must continue to declare `Depends(internal_principal)`.
- Added an AST guard requiring each public demo route to consist only of a docstring, import of its exact reviewed `app.demo` synthetic helper, and a direct zero-argument return call, with no `await`, commit `961a99bac31912ddcfd72d473020edaa75c217a6`. This checks route wrapper structure, **not** the internals of `app.demo`.
- **Not yet executed** against an authentic materialized `app/main.py` checkout in the ChatGPT lab; no claim of green route suite. No real business-route HTTP, IdP, actor→tenant→resource ACL, PostgreSQL or upstream qualification. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Public synthetic demo helper static review

- Fetched actual `app/demo.py` from Draft branch and materialized the complete source in the ChatGPT internal partial lab. Both public helpers construct fixed synthetic inputs, call reused pure correlation/evidence preview helpers and label results non-authoritative.
- Created `tests/test_demo_source_guard.py` to AST-check the public demo helper module's permitted imports and call forms, and to mutation-test introduction of a network import/call or changing `authoritative=False` to `True`. Executed `python -m pytest -q tests/test_demo_source_guard.py`: **3 passed in 0.04s**.
- Promoted the new static test to GAMMA branch, commit `3d2c11b0898a81cae649a5d76ab125cca191bb02`.
- Static review of demo source only. The reused helper implementations and real business-route HTTP are **not** qualified by this test; `tests/test_route_security_static.py` still needs execution against full `app/main.py`. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Route inventory alternate-registration guard

- Fetched actual `app/main.py` from GitHub; textual declaration scan found **21 `@app.get/post/...` routes**, no duplicate method/path pairs, and no existing `include_router`, `add_api_route`, `APIRouter` or `mount` calls. This is source-text inspection, not execution of the full route AST suite.
- Added `_assert_no_unreviewed_route_registration` to `tests/test_route_security_static.py`, rejecting alternative FastAPI route registrations and non-`app` route decorators, commit `a864c0639cf11f11c3eefe7a134f3ef4c9435f0f`.
- Ran representative AST guard logic in the ChatGPT internal lab against one allowed and six forbidden source snippets: **7 passed in 0.03s**. These were local targeted snippets, not the committed test file against authentic `app/main.py`.
- Extended guard to `api_route`, websocket and route variants, commit `2abd1ff5b8442925f8a80d4eea54d241468bcec6`; corrected escaping in the new mutation fixtures so the snippets are valid Python, commit `d18b671f5a9be96bcbc95b6ae0b97e846e646a2a`. The extended committed suite is **not yet executed** in the lab.
- This is inventory integrity only; it does not qualify the actual business-route HTTP behavior, actor→tenant→resource ACL, PostgreSQL, upstream or real IdP. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Duplicate and keyword-path route inventory bypass guards

- Reviewed the authentic `tests/test_route_security_static.py` after prior changes. Found that comparing a `set` of method/path tuples would miss duplicate declarations, and `_routes()` ignores decorators using keyword `path=` rather than positional path.
- Updated the inventory check to reject duplicate method/path registrations and tightened the alternate-registration AST guard to reject `@app.get/post/put/patch/delete` declarations without exactly one positional string path or with keyword `path`, commit `e38b11f6aa57155e1160aafa13782f64b0660c54`. Repaired newline escaping in new mutation snippets, commit `45c035c34793787c5dd087a59c163512f6cd799b`.
- Executed a **representative local AST guard implementation** against one accepted route and ten rejected route declarations (including keyword path, duplicate path keyword, api_route, websocket and alternate router registration): **11 passed in 0.05s**. This was not the exact committed route test file, nor a complete `app/main.py` test run.
- No actual business-route HTTP, real IdP, actor→tenant→resource ACL, PostgreSQL or upstream qualification. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Static Gateway dependency shape bypass fixed

- Inspected authentic `tests/test_route_security_static.py`: its `_uses_internal_principal` previously walked arbitrary AST descendants of parameter defaults and annotations. A syntactically present but inert `Depends(internal_principal)`, e.g. `p=(Depends(internal_principal), None)[1]`, could incorrectly satisfy the static guard without being an actual FastAPI dependency.
- Replaced the broad AST walk with a direct default `Depends(internal_principal)` check or `Annotated[..., Depends(internal_principal)]` metadata check, requiring exactly one dependency positional argument and no extra keywords; added six positive/negative source mutation cases. Commit `26fbf4000e68f62bccca69d30ef34734fc130596`.
- Ran a standalone local Python AST implementation of the same predicate with six scenarios in the ChatGPT internal lab: `python -m pytest -q` => **1 test passed in 0.03s** (the test exercises six cases). **Not** the exact committed test file against full authentic `app/main.py`; no full route-suite claim.
- No real business-route HTTP, actor→tenant→resource ACL, PostgreSQL, upstream or real IdP qualification. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Fail-closed tenant API cache middleware AST guard

- Inspected authentic `app/main.py` and `tests/test_route_security_static.py`. The old cache middleware static check only searched source for the strings `"/api/v1/"`, `"Cache-Control"` and `"no-store"`; it could pass if the strings were inert and the response header assignment removed.
- Added an exact AST-shape guard for the reviewed `prevent_tenant_api_caching` middleware, including its FastAPI decorator, awaited `call_next`, tenant API path condition, live health exclusion, actual response header assignment, and response return. Added mutation tests for four bypasses, commit `cb4d92902f09d5b2fed218f8da754c13f723cba7`.
- Ran equivalent isolated Python AST checks in the ChatGPT internal lab: **5 scenarios passed** (one valid, four mutations rejected). **The complete committed test file has not yet been run against a materialized authentic `app/main.py`**; no claim of full suite success.
- This is a source-change tripwire, not runtime HTTP cache verification. No real business-route HTTP, actor→tenant→resource ACL, PostgreSQL or upstream qualification. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Consolidated partial authentic-source lab regression

- Ran `python -m pytest -q tests/test_demo_source_guard.py tests/test_python_source_parse_contract.py tests/test_canonical_acl_hard_hold_static.py tests/test_upstream.py tests/test_tenant_scope_guard.py tests/test_redaction.py` in `/mnt/data/gamma_authentic_subset`: **70 passed in 0.44s**.
- This partial lab contains selected source/test files manually copied from the GAMMA branch, not an authenticated complete checkout. The 70 passing tests cover demo source guard, source parser, canonical HOLD, upstream, tenant scope and redaction only.
- The full `tests/test_route_security_static.py` against authentic `app/main.py` and real business-route HTTP tests remain **unexecuted**. Prior focused AST mutation results must not be represented as full route-suite success.
- No GitHub Actions, real IdP, actor→tenant→resource ACL, PostgreSQL, upstream LIVE, merge or deploy. **HOLD / NO_GO**.

### 2026-11-13 — Full authentic route security static suite finally executed

- Materialized complete `app/main.py` and `tests/test_route_security_static.py` in the ChatGPT internal partial lab, copied from the exact GitHub branch contents. Verified each local file's Git blob SHA-1 against GitHub `fetch_file`: `app/main.py` = `a207277da659ceea4b2706f4e27af1366a6eb1fb` (13,033 bytes), route test = `03b6554ee04b0f3edec406e7d267ef91c159ad78` (12,126 bytes).
- Ran the **actual complete route test file** against the **exact authentic main.py source**: `python -m pytest -q tests/test_route_security_static.py` => **8 passed in 0.07s**. This supersedes earlier caveats that the full route AST suite was unexecuted.
- Ran consolidated partial-lab suite including route guard, demo guard, parser, canonical HOLD, upstream, tenant scope and redaction: **78 passed in 0.38s**.
- Static AST checks only: this is not actual FastAPI business-route HTTP integration, real IdP/gateway, actor→tenant→resource authorization, PostgreSQL tenant isolation or upstream contract qualification. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Actual GAMMA FastAPI business-route HTTP isolation lab

- Created a new local isolated HTTP lab at `/mnt/data/gamma_business_http_lab` using the complete actual `app/main.py`, `app/security.py` and `app/settings.py` source previously fetched from GitHub. Imports for unavailable DB models/session, OpenSearch, GLPI, upstream, pure business models/functions and public demo helpers were stubbed in memory; **the route wrappers, FastAPI middleware and gateway verification dependency were not stubbed**.
- Exercised all **18 tenant-protected business route declarations** through FastAPI TestClient with a service key but no signed gateway assertion, including path parameter substitution. Each returned **HTTP 401** and `Cache-Control: no-store`. The 3 public health/demo endpoints returned HTTP 200 (the demo helpers are stubbed, so their actual business payloads were not tested).
- Exercised signed HMAC gateway assertions against the **real metrics route**: correctly signed request bound to method/path reached expected **HTTP 501** (unimplemented feature); correctly signed assertion bound to a different path returned **HTTP 401**. Both responses included `Cache-Control: no-store`.
- Command `cd /mnt/data/gamma_business_http_lab && pytest -q test_real_main_http.py` => **23 passed in 0.70s**.
- **Qualification limit:** isolated partial-source TestClient harness, not a full authentic repo checkout or real DB/business adapter integration; test harness currently local only, not yet promoted into the GitHub repo. No external service or PostgreSQL was contacted. Actor→tenant→resource ACL, real IdP, PostgreSQL, upstream, replay and full integration remain unqualified. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Real FastAPI route HTTP tenant mismatch and forged header checks

- Extended the local partial-source `/mnt/data/gamma_business_http_lab/test_real_main_http.py` harness (actual `app/main.py` and `app/security.py` with isolated external module stubs) to exercise two more real route wrapper behaviors:
  - Signed actor POST to `/api/v1/incidents/evidence/preview` with an item carrying a different tenant ID returns **HTTP 403** and `Cache-Control: no-store`.
  - Signed actor POST to `/api/v1/observability/metrics/query` with a conflicting forged `X-Tenant-ID` header still reaches the protected stub implementation and returns **HTTP 501**, rather than accepting the header as principal authority.
- Local command `cd /mnt/data/gamma_business_http_lab && python -m pytest -q test_real_main_http.py`: **25 passed in 0.60s** (previously 23).
- **Scope:** this test harness is still local, not promoted to the GitHub repository. Business schema/model dependencies and external adapters are stubbed; actual route wrappers, middleware and signed gateway dependency are used. This does not prove independent actor→tenant membership, source ACL, real PostgreSQL tenant isolation, IdP or upstream contracts.
- No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Promote isolated real FastAPI route HTTP probe into version control

- Added `tests/support/real_route_http_probe.py` with 25 parametrized real FastAPI route wrapper tests: 18 protected routes reject unsigned service-key-only callers with 401, 3 public routes return 200, signed actor reaches the metrics 501 placeholder, wrong signed path returns 401, cross-tenant evidence preview returns 403, and forged X-Tenant-ID cannot override signed principal. All protected API responses checked for `Cache-Control: no-store`. Commit `ff7828a97cf7bf4e20776a0e79fc1be6aac4ddae`.
- Added `tests/test_real_route_http_isolation.py` which runs the probe as a pytest subprocess to prevent the probe's in-memory stubs of unavailable business adapters from leaking into normal suite imports. Commit `a83b15921614383ef5e6778bfd9e9340ea8a2c04`.
- The original 25-case local lab passed, but **the newly committed probe and subprocess wrapper have not yet been executed as exact repository files**. No claim of committed test pass. Run `python -m pytest -q tests/test_real_route_http_isolation.py` in a complete source environment as next verification.
- Source-boundary and simulated-adapter limits remain: no real IdP, actor→tenant→resource ACL, PostgreSQL or upstream. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Isolated HTTP subprocess launcher smoke test

- Re-ran original local `/mnt/data/gamma_business_http_lab/test_real_main_http.py`: **25 passed in 0.66s**.
- Placed that previously verified local probe under `tests/support/real_route_http_probe.py` in the local lab and created a local wrapper matching the committed subprocess launcher's implementation. Ran `python -m pytest -q tests/test_real_route_http_isolation.py`: **1 passed in 4.26s**; subprocess itself verified `25 passed`.
- **Important provenance limit:** the subprocess used the original local 25-test source copied to the support path, not a byte-for-byte materialization of the newly committed `tests/support/real_route_http_probe.py`. Therefore the exact committed support probe is **not yet qualified**, despite the successful launcher smoke test. Avoid reporting the GitHub-committed 25-case probe as executed.
- No GitHub Actions, PostgreSQL, external services, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Signed Gateway HMAC tampering regression on actual metrics HTTP route

- Added one real-route TestClient regression for a tampered HMAC signature: correctly signed `POST /api/v1/observability/metrics/query` assertion has its signature altered and must return HTTP **401** with `Cache-Control: no-store`. Versioned probe commit `c91db6b3eb47936f656c5cd0e2ec58a735817978`; subprocess launcher expects **26 passed**, commit `34a6088f1fc9118fb75b66f2cd9e953801c8b6bb`.
- Internal lab: appended equivalent test to original local source and ran `python -m pytest -q test_real_main_http.py`: **26 passed in 0.61s**. Copied local 26-case source to local subprocess support path and ran `python -m pytest -q tests/test_real_route_http_isolation.py`: **1 passed in 3.52s**, checking subprocess `26 passed`.
- **Provenance limit remains:** the local 26-case source is equivalent in intent but is **not** a byte-for-byte verified copy of the GitHub-committed support probe. Exact committed support probe still awaits isolated execution and may need fixes.
- No GitHub Actions, PostgreSQL, external services, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Gateway method and expiry negative HTTP probes

- Added two versioned HTTP scenarios in `tests/support/real_route_http_probe.py`: valid HMAC bound to GET must be rejected for POST metrics, and correctly signed expired HMAC must be rejected. Both require HTTP 401 and `Cache-Control: no-store`. Commit `bce2e5f0363d827b0417de97a4900b19227e539e`.
- Updated `tests/test_real_route_http_isolation.py` subprocess expected count to **28**, commit `eac5ca7915e664eae1db5c38582046b7bd434437`.
- Local 28-case equivalent HTTP probe: **28 passed in 0.83s**. Initial local run failed because the original local token helper ignored injected expiry timestamps; corrected the local helper to apply explicit issued/expiry values. Local subprocess wrapper initially retained an old 26-test assertion, then corrected it: **1 passed in 3.78s**, inner probe 28 passed.
- **Provenance limit:** these executions used local adapted files, not byte-for-byte verified GitHub-committed `tests/support/real_route_http_probe.py`. No exact-committed-file pass claim. No external adapters, PostgreSQL or real IdP/ACL qualification. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — HTTP probe provenance check and missing workload-key regression

- Compared local lab `tests/support/real_route_http_probe.py` Git blob SHA `36cc8a69715701fdbab444ba706918bb01de6a08` against GitHub `42c010f9c684f7c265b89d957d6edaafbff99fee` (prior to this cycle's changes); local wrapper SHA `c79e05d917cee5af62d602df18eef1c42b57b1c3` versus GitHub `d314068a0494a0b98e69b916240f612e5b023b46`. **Neither local file is byte-identical to the committed version.**
- Direct `pytest -q tests/support/real_route_http_probe.py` in the partial lab failed at collection (`ModuleNotFoundError: app`); `python -m pytest -q tests/support/real_route_http_probe.py` passed **28** before adding the new case, and the local subprocess launcher passed **1**. The committed wrapper already uses `sys.executable -m pytest`.
- Added a 29th versioned HTTP test: a correctly signed Gateway assertion **without the internal workload service key** must return HTTP **401** and `Cache-Control: no-store`. Probe commit `0cd942d1d8c5d47ec95affe768580ba096de1cc5`; wrapper expected count changed to **29**, commit `a028d77733451eda7adac9feb3fec13774ecfb17`.
- Added equivalent case to the local lab and ran `python -m pytest -q tests/support/real_route_http_probe.py tests/test_real_route_http_isolation.py`: **30 passed in 4.45s** (29 direct HTTP cases + 1 subprocess wrapper which itself runs 29). **Still not an exact committed-file execution**.
- No GitHub Actions, real actor→tenant→resource ACL, PostgreSQL, upstream, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Exact committed HTTP probe and subprocess launcher SHA-qualified

- Materialized the complete current GitHub `tests/support/real_route_http_probe.py` in `/mnt/data/gamma_business_http_lab`; computed Git blob SHA-1 on the local bytes and verified **exact equality** with GitHub's `fetch_file` SHA: `db8416cad46b2ab3369079ee98cadae351e917e7` (7,668 bytes). The lab's `app/main.py` also matches the previously verified GitHub blob `a207277da659ceea4b2706f4e27af1366a6eb1fb`.
- Executed the **exact committed probe file**, `python -m pytest -q tests/support/real_route_http_probe.py`: **29 passed in 0.94s**. This closes the previously documented source-provenance gap for the HTTP probe itself.
- Materialized the exact current committed `tests/test_real_route_http_isolation.py`; local Git blob SHA matches GitHub `2e463f228623e223be8d418d45d58874b49aff29` (616 bytes). Executed `python -m pytest -q tests/test_real_route_http_isolation.py`: **1 passed in 3.31s**; the subprocess executed the same 29 HTTP checks.
- **Limits:** partial isolated source lab with stubbed unavailable business/DB/upstream/demo modules; the exact probe and wrapper are now source-verified, but this is not full repository integration, independent actor→tenant→resource authorization, real IdP, PostgreSQL tenant isolation, or approved upstream contracts. No GitHub Actions, DB, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Real evidence model/normalizer in signed FastAPI route probe

- Removed the in-memory fake `app.reused.evidence` module from the versioned isolated HTTP probe. The real `app.main` evidence-preview route now imports `EvidenceInput` and `normalize` from `app/reused/evidence.py`. Cross-tenant negative test now supplies a structurally valid evidence item rather than a tenant-only fake model. Added a signed same-tenant positive test asserting HTTP 200, `UNVERIFIED` integrity, correct tenant, `persisted=False`, `live_remediation_authorized=False`, and `Cache-Control: no-store`. Probe commits `2ca06bf06b25846f5f427bc95c380747e1be4b86` and `3d527561666662d64d844887c71d87dd68183802`.
- Subprocess wrapper now expects **30 passed**, commit `ce0a0b931f6ffd89d154a806280056fd4021176b`.
- ChatGPT internal partial lab: manually reconstructed the evidence model/normalization logic from GitHub source, modified the local probe equivalently, ran `python -m pytest -q tests/support/real_route_http_probe.py tests/test_real_route_http_isolation.py`: **31 passed in 3.97s** (30 direct HTTP scenarios + one subprocess launcher). **Important:** this run uses a manually reconstructed `app/reused/evidence.py`, not a SHA-verified exact copy; the current committed probe also has not been SHA-verified in this cycle. Do not claim exact GitHub file execution for this new 30-case revision.
- The test confirms the real route's tenant check and evidence preview contract in an isolated lab, not independent actor→tenant→resource authorization or source integrity. Other business adapters are still stubbed; no PostgreSQL, real IdP, upstream, GitHub Actions, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Evidence schema and dedup HTTP contract checks

- Extended versioned `tests/support/real_route_http_probe.py` with two real-route tests: a tenant-only incomplete evidence object is rejected at Pydantic validation with **422** (rather than exercising a fake tenant-only model), and two identical same-tenant evidence objects produce one preview item, `duplicates=1`, `integrity=UNVERIFIED`, `persisted=False`, `live_remediation_authorized=False`. Both require `Cache-Control: no-store`. Commit `3d4289a5731757f8326ba83b6ab58ca748f01b24`.
- Updated `tests/test_real_route_http_isolation.py` expected count to **32**, commit `ba12f953dc4b17feafca9192107c2f0ca75dbb04`.
- ChatGPT internal lab `/mnt/data/gamma_business_http_lab` with the new two cases: `python -m pytest -q tests/support/real_route_http_probe.py tests/test_real_route_http_isolation.py` => **33 passed in 3.89s** (32 direct HTTP + 1 subprocess wrapper). This lab's `app/reused/evidence.py` is a manually reconstructed implementation, **not Git-blob-SHA verified**, and the newly committed probe bytes were not re-materialized for SHA verification this cycle. No exact-committed-file pass claim.
- No PostgreSQL, real IdP, independently verified actor→tenant→resource ACL, upstream access, GitHub Actions, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Mixed-tenant evidence batch and timezone-aware input guards

- Added real-route HTTP negative cases: a batch containing one correctly signed same-tenant evidence item and one other-tenant item must fail as a whole with HTTP 403; a same-tenant item with a timezone-naive `observed_at` must fail validation with HTTP 422. Both require `Cache-Control: no-store`. Probe commit `9c6dad91a752668e7f002cb9a8329d7595281c11`.
- Subprocess wrapper updated to expect **34 passed**, commit `891019a97b2c91eb076dba97b6108801b19c2208`.
- Internal partial lab: `python -m pytest -q tests/support/real_route_http_probe.py tests/test_real_route_http_isolation.py` => **35 passed in 3.65s** (34 HTTP + wrapper). The local wrapper Git blob SHA **dd425de9a2e53599c6205dfa41dc6b056586aa78** matches the committed wrapper; the local probe SHA `c7c8cedf908df8e508cae2f7f0ba5373fdf2d57c` does **not** match committed `61f266f848aba3cc53454b2ca500546a4a49b9e0`, and local evidence module SHA `a55aced875661fee23f356ad335821e2c48c09c4` does **not** match committed `7e5b24cc300e1d956ae87494cd1c8df6129f6b2f`. Local evidence module is still reconstructed. No exact-source qualification claim for these two.
- Remaining gates: independent actor→tenant→resource authorization, actual upstream ACL, real IdP/gateway, PostgreSQL 16 HTTP isolation, approved contracts, functioning CI. No GitHub Actions, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Conflicting evidence versions fail conservatively in HTTP preview

- Added an isolated real-route HTTP regression submitting two same-tenant evidence records with identical source/external identity but conflicting payloads. The response must be 200 advisory-only with `duplicates=1`, one representative, `state=UNKNOWN`, `integrity=UNVERIFIED`, `persisted=False`, `live_remediation_authorized=False`, and `Cache-Control: no-store`. Commit `f442af6dc22d56bde60afedbe9f857b26a18e2aa`.
- Updated subprocess wrapper expectation to **35 passed**, commit `d29dd7a24addaa53e4710b7afac5dd7880f8d9fd`.
- Internal partial lab `python -m pytest -q tests/support/real_route_http_probe.py tests/test_real_route_http_isolation.py`: **36 passed in 3.73s** (35 HTTP cases + one launcher). **Provenance:** the local probe and evidence normalizer remain manually adapted and have not been byte-for-byte verified against the new GitHub versions; do not present this as a full exact-source integration test.
- No real IdP, independent actor→tenant→resource ACL, upstream source authorization, PostgreSQL, GitHub Actions, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Mixed-tenant evidence must not enter normalization

- Added a targeted FastAPI HTTP regression that monkeypatches **`app.main.normalize_evidence`**, the imported function actually called by the route (rather than `app.reused.evidence.normalize`, which would be a vacuous spy). A batch containing one signed-tenant evidence item and one foreign-tenant item must return HTTP **403** with `Cache-Control: no-store` and **zero normalizer invocations**. Commit `75a4d55d09639ee22d50c0abb7748e31f6ca02b8`.
- Updated subprocess launcher expectation to **36 passed**, commit `4e48d572ba49e0ff1082d1e630aed165cd1d8443`.
- ChatGPT internal partial lab: targeted case **1 passed**; full `python -m pytest -q tests/support/real_route_http_probe.py tests/test_real_route_http_isolation.py` => **37 passed in 3.81s** (36 HTTP cases + 1 launcher). Uses locally adapted source and reconstructed evidence normalizer, not a fresh byte-identical checkout.
- No GitHub Actions, PostgreSQL, independent actor→tenant→resource ACL, upstream access, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Real canonical HOLD adapter through signed FastAPI HTTP routes

- Removed the fake `app.reused.upstream` module from the isolated real-route HTTP probe. Added four signed GET route cases for `/api/v1/canonical/{resource}/snapshot`: allowlisted `core`, `evidence`, `twin` must return **503**; unknown `unlisted` must return **404**. Each requires `Cache-Control: no-store`; monkeypatching `httpx.AsyncClient` to raise ensures the request path does not instantiate an upstream HTTP client. Probe commit `0ae45de3832cf5ab74e24450d9c4ed9a42b8056a`.
- Updated subprocess launcher expected count to **40**, commit `9e86aa4933cd2600a6dd86d0d763b0e88ada35c8`.
- ChatGPT internal partial lab: copied `app/reused/upstream.py` from the fetched GitHub source into the isolated lab and ran `python -m pytest -q tests/support/real_route_http_probe.py`: **40 passed in 0.96s**. After updating the local launcher, `python -m pytest -q tests/support/real_route_http_probe.py tests/test_real_route_http_isolation.py`: **41 passed in 3.65s**. The copied upstream source has local Git blob SHA `8aa5ba94ef422e35ab86863c4319ea422b880e46`; no GitHub SHA comparison was completed in this cycle. Other business modules remain stubbed.
- These tests confirm the current intentional **HOLD** for canonical reads, not that actor→tenant→resource ACL or upstream contracts are qualified. No GitHub Actions, PostgreSQL, external upstream calls, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Canonical HOLD survives accidental legacy enable flag

- Confirmed the exact local `app/reused/upstream.py` Git blob SHA **8aa5ba94ef422e35ab86863c4319ea422b880e46** equals the fetched GitHub blob SHA. This closes the upstream adapter source-provenance gap.
- Added three parametrized signed HTTP tests with `settings.enable_canonical_reads=True`, a configured token and plausible HTTPS origins. `core`, `evidence` and `twin` must still return **503** with `Cache-Control: no-store`. Both `httpx.AsyncClient` and `httpx.Client` are replaced with fail-fast guards to detect accidental outbound client construction. Probe commit `3898bb1d7312657428e03cc3a8881442b823a9ae`; subprocess launcher expects **43 passed**, commit `38ccb150b5fba3406c96e07608dc23eb37430864`.
- Internal partial lab: `python -m pytest -q tests/support/real_route_http_probe.py` => **43 passed in 0.77s**; combined probe + launcher => **44 passed in 3.70s**. This cycle's local probe is adapted, not SHA-identical to the newly committed probe; local evidence normalizer is also reconstructed. No full-checkout or production claim.
- No GitHub Actions, PostgreSQL, real upstream traffic, independent actor→tenant→resource ACL, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Reject evidence size and freshness-policy violations before normalization

- Added three isolated FastAPI HTTP regressions on the real evidence-preview route: **501** valid same-tenant evidence items (maximum 500), `max_age_seconds=0`, and `max_age_seconds=86401` (allowed 1..86400) must all return HTTP **422** with `Cache-Control: no-store`. A spy on **`app.main.normalize_evidence`** asserts **zero invocations** for each invalid request, verifying that Pydantic request validation precedes business normalization. Probe commit `f08709dd6d469390ef2aa0a35629c10394063f7d`.
- Updated subprocess launcher expected count to **46 passed**, commit `31adbfda08ea94fd2cf7eacc4626220578475f8e`.
- ChatGPT internal partial lab: `python -m pytest -q tests/support/real_route_http_probe.py tests/test_real_route_http_isolation.py` => **47 passed in 4.12s** (46 HTTP cases + launcher). Lab includes real FastAPI route and gateway dependency but stubbed other business/DB integrations; evidence module remains locally reconstructed. The newly committed probe was not independently SHA-materialized in this cycle.
- No GitHub Actions, PostgreSQL, independently verified actor→tenant→resource ACL, upstream reads, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Exact evidence normalizer provenance and JSON-size HTTP guards

- Replaced the manually reconstructed local `app/reused/evidence.py` with the exact fetched GitHub source. `git hash-object app/reused/evidence.py` equals GitHub blob **7e5b24cc300e1d956ae87494cd1c8df6129f6b2f**. Existing isolated HTTP suite remained green (**47 passed in 3.85s**).
- Added two signed FastAPI HTTP cases for over-limit JSON `payload` (65,536-byte ceiling) and `provenance` (8,192-byte ceiling). Each must return HTTP **422**, `Cache-Control: no-store`, and zero calls to `app.main.normalize_evidence`. Probe commit `f4d6253ed3549d5916b2b48779f389a7e0d0632a`; subprocess launcher expects **48 passed**, commit `9e94cc4946ac57f73e918ac6c2e9fb57e38c6911`.
- ChatGPT internal partial lab: `python -m pytest -q tests/support/real_route_http_probe.py tests/test_real_route_http_isolation.py` => **49 passed in 4.21s** (48 HTTP cases + launcher). Evidence and upstream adapter sources now have exact matching Git blob SHA; probe file itself is still a locally adapted copy, not independently byte-verified against the new GitHub blob. Other business/DB integrations are stubbed.
- No GitHub Actions, PostgreSQL, independently verified actor→tenant→resource ACL, upstream reads, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Evidence normalizer determinism and freshness boundary tests

- Reviewed the existing `tests/test_evidence_normalization.py` (14 existing cases covering non-authoritative output, stale/future inputs, tenant separation, conflicts, bounds, timestamp validity, JSON limits, NaN and provenance fingerprints).
- Added three regression tests: conflicting duplicate output must be independent of input arrival order; freshness is inclusive at `now` and exactly `max_age_seconds` but rejects future and one-second-stale evidence; differing payloads for the same claim across distinct event IDs must leave both states `UNKNOWN`. Commit `6ea48eb47d3690eaca7fbe594610d61c49834e10`.
- Ran four focused tests in the internal Python lab against a local isolated copy of the evidence-normalizer implementation: **4 passed in 0.05s** (conflict arrival-order determinism, same-claim conflict, freshness boundaries, non-authoritative invariants). The lab's focused file is not the exact committed test file; **the full committed `tests/test_evidence_normalization.py` has not been executed in this cycle**.
- No GitHub Actions, PostgreSQL, real IdP, independent actor→tenant→resource ACL, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Evidence normalization suite executed locally; exactness caveat corrected

- Materialized the current GitHub `app/reused/evidence.py` source into `/mnt/data/gamma_evidence_unit/app/reused/evidence.py`; Git blob hash matches exactly: **7e5b24cc300e1d956ae87494cd1c8df6129f6b2f**.
- Reconstructed the current 18-test `tests/test_evidence_normalization.py` locally from fetched GitHub content and ran `python -m pytest -q`: **18 passed in 0.07s**. However local Git blob SHA **3b6c1c9a9876646efd154f75475ccbd5d007bc4b** does not match the current GitHub test blob SHA **a6628bc859c8aaf2997a37407767554453b48cff** (local file is 5 bytes longer). Therefore this is a semantically equivalent local test copy, **not an exact-byte execution of the committed test file**. Prior handover reference to 17 tests is corrected: current file contains 18 tests.
- No GitHub Actions, PostgreSQL, independent actor→tenant→resource ACL, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Correlation/evidence join qualification extended

- Materialized exact GitHub sources into `/mnt/data/gamma_evidence_unit`; local Git blob hashes match:
  - `app/reused/correlation.py`: **53c1fdf1b16485d6f26d8f3b7337abc46fe5beb8**
  - `app/reused/correlation_evidence.py`: **083f56d1e91487f95dc7b431a971497722e78c85**
  - `app/reused/evidence.py`: **7e5b24cc300e1d956ae87494cd1c8df6129f6b2f**
- Added two versioned correlation/evidence regressions: cross-tenant evidence must be rejected **before** the correlation function is called; a fully covered and internally consistent join must still retain `evidence_state=UNVERIFIED`, per-item `integrity=UNVERIFIED`, `persisted=False`, and `live_remediation_authorized=False`. Commit `ded9a4f01d3efc7a819dabd193ec7638021beaa8`.
- Internal lab `python -m pytest -q`: **26 passed in 0.07s** — 18 normalization cases plus 8 focused correlation/evidence join cases (exact application modules copied from GitHub). The 18-case local normalization test file still has a 5-byte content difference from the committed test file's Git blob; its SHA does not match, so no exact test-file execution claim. The 8 correlation tests are focused local equivalents, not the full committed `tests/test_correlation_evidence.py`.
- No GitHub Actions, PostgreSQL, real IdP, independent actor→tenant→resource ACL, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Correlation time-window, timezone and source-identity boundaries

- Added three versioned tests to `tests/test_correlation.py`:
  - Correlation window is inclusive at exactly 300 seconds and splits at 301 seconds.
  - Two timezone representations of the same instant produce the same canonical group ID and UTC output timestamp.
  - The same external event ID from distinct sources is not deduplicated (identity is the exact `(source, external_event_id)` pair).
  Commit: `874f81b3852a9b83df580d5f5b146bce46ce6b2f`.
- Internal lab `/mnt/data/gamma_evidence_unit`: confirmed local Git blob hashes exactly match current GitHub application sources:
  - correlation `53c1fdf1b16485d6f26d8f3b7337abc46fe5beb8`
  - correlation/evidence join `083f56d1e91487f95dc7b431a971497722e78c85`
  - evidence normalizer `7e5b24cc300e1d956ae87494cd1c8df6129f6b2f`
- Added equivalent focused cases to the local lab and ran `python -m pytest -q`: **30 passed in 0.06s** (18 normalization tests + 12 correlation/evidence lab tests). The local join test file is a focused lab suite, not byte-identical to committed `tests/test_correlation.py`; do not claim execution of the exact full committed correlation test module. The three new cases are represented equivalently and the production modules are exact-source verified.
- No GitHub Actions, PostgreSQL, real IdP, independent actor→tenant→resource ACL, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Rolling correlation windows and duplicate identity regressions

- Added four tests to `tests/test_correlation.py`: adjacent rolling gaps (events at 0/250/500 seconds remain one group for a 300-second window), a 301-second adjacent gap starts a new group, duplicate counts are scoped to exact source+event identity, and conflicting duplicate representatives/results are independent of arrival order while remaining non-persistent/non-live. Commit `4edd2d86eeb0476338dbaf8c190690a4c45b1ba1`.
- Internal lab copied to writable `/tmp/gamma_correlation_lab`, retaining exact-source verified correlation/evidence modules. Added equivalent focused cases and ran `python -m pytest -q`: **34 passed in 0.08s** (prior 30 + four new focused checks). This does not claim byte-identical execution of the complete committed `tests/test_correlation.py`; the local correlation/evidence lab remains a focused subset.
- No GitHub Actions, PostgreSQL, real IdP, independent actor→tenant→resource ACL, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Correlation grouping namespaces and collision boundaries

- Added four tests to `tests/test_correlation.py`:
  - Distinct services group together only when they explicitly share the same non-null CI identity; distinct CI IDs remain separate.
  - Environment and symptom are hard grouping boundaries.
  - CI identity and service-name identity use separate namespaces and cannot collide merely because their strings match.
  - Conflicting duplicate accounting is scoped to exact `(source, external_event_id)`; another source with the same external ID remains an independent event.
  Commit: `8e0b70dcb106242ecdf466fc51b655f6caaf1736`.
- Internal isolated lab `/tmp/gamma_correlation_lab` using exact-source-verified `app/reused/correlation.py`, `correlation_evidence.py`, and `evidence.py`: added equivalent focused checks and ran `python -m pytest -q`: **38 passed in 0.10s** (34 previous focused cases + 4 new grouping-boundary cases).
- **Qualification limit:** these four new cases were run as equivalent local focused tests, not as the byte-identical complete committed `tests/test_correlation.py`; no full repository suite was executed. No PostgreSQL, IdP, independently enforced actor→tenant→resource ACL, GitHub Actions, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Multi-group Evidence joins and conservative temporal/source mismatch

- Added three tests to `tests/test_correlation_evidence.py`:
  - Two correlation groups with distinct symptoms/events receive only their exact `(source, external_event_id)` evidence; both groups are covered but remain `UNVERIFIED`, and the preview remains non-persistent/non-live.
  - An evidence item sharing an external ID but coming from the wrong source is not cross-linked; the alert remains uncovered and the evidence is reported unmatched.
  - Future-dated evidence can be identity-covered but must make the group `UNKNOWN` and join inconsistent.
  Commit: `6e098f552c5423b311911d0dec5dd6b2e8d6b1e9`.
- Internal lab copied to writable `/tmp/gamma_join_lab`, using exact-source-verified `correlation.py`, `correlation_evidence.py`, and `evidence.py`. Added equivalent focused tests and ran `python -m pytest -q`: **33 passed in 0.09s**. This is a focused local suite, not execution of the exact committed `tests/test_correlation_evidence.py` file or the full repo suite.
- No PostgreSQL, IdP, independent actor→tenant→resource ACL, GitHub Actions, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Multi-incident evidence claims and stale-join semantics

- Added three tests to `tests/test_correlation_evidence.py`:
  - One exact source-event identity claimed by two distinct incident IDs is **not** collapsed as a duplicate (the evidence normalizer's dedup identity includes `incident_id`); both claims remain visible, group state is `UNKNOWN`, join coverage may be complete but consistency is false, and persistence/LIVE remain disabled.
  - Reversing those two incident claims leaves the complete preview result unchanged.
  - Stale evidence can be identity-covered (no missing or unmatched item) while its group remains `UNKNOWN`; join completeness is true but consistency is false.
  Commit: `9dd36e6a3244e31e67d02dfb20bda90cd24e5506`.
- **Execution status:** these three committed tests have not been executed in the internal lab in this cycle. No test-pass count is claimed. Previous focused lab result remains 33 passed (from the preceding cycle), not including these additions.
- No GitHub Actions, PostgreSQL, real IdP, independently enforced actor→tenant→resource ACL, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Mixed-tenant rejection is fail-fast before correlation and normalization

- Added three tests to `tests/test_correlation_evidence.py`:
  - A mixed-tenant evidence batch (one valid tenant item plus one foreign-tenant item) raises `PermissionError` before either `correlate` or `normalize` is invoked.
  - An all-foreign-tenant batch is rejected before either processing stage.
  - A single source-event identity claimed by two incident IDs remains fully visible (no false duplicate/unmatched count), but is explicitly `UNKNOWN`; join coverage is complete while consistency remains false, and persistence/LIVE remain disabled.
  Commit: `3bdc37335cb4dec080459a611d94de4d05a4543c`.
- Internal lab executed three focused equivalent tests against exact GitHub application modules in `/mnt/data/gamma_evidence_unit`: **3 passed in 0.05s**. Verified local Git blob hashes against GitHub source hashes: `correlation.py` **53c1fdf1b16485d6f26d8f3b7337abc46fe5beb8**, `correlation_evidence.py` **083f56d1e91487f95dc7b431a971497722e78c85**, `evidence.py` **7e5b24cc300e1d956ae87494cd1c8df6129f6b2f**. The focused test file is a local equivalent, not the exact committed test module; no full suite execution is claimed.
- No GitHub Actions, PostgreSQL, real IdP, independent actor→tenant→resource ACL, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Gateway assertion policy and TTL fail-closed boundary tests

- Extended `tests/test_gateway_auth_extra.py` with 11 parameterized security cases:
  - TTL values 1, 30 and 60 seconds are accepted at the exact configured ceiling.
  - Misconfigured TTL values 0, -1, 61, boolean `True`, and float 1.5 fail closed with HTTP 503.
  - Missing issuer or audience policy fails closed with HTTP 503.
  - A 31-character HMAC secret fails closed with HTTP 503 (minimum is 32 UTF-8 bytes).
  Commit: `712a4d9665495d6b824a04c8f73d8721c0f37df3`.
- Internal lab `/mnt/data/gamma_security_lab`: added equivalent tests and ran `python -m pytest -q tests/test_gateway_auth_extra.py`: **29 passed in 0.26s** (18 existing + 11 new cases).
- **Exact-source caveat:** local `app/security.py` blob `4f5852e02c443ee02d41273ff81ed96f42363ae4` does not match current GitHub source blob `06f7bd7bb309133823efefd68dddb8d7784d90ca`; local `app/settings.py` blob `0572953d116fa1b525cbaa693d2941384b839767` is also not newly verified against GitHub in this cycle. Thus the 29-pass result is a local compatibility check against the existing lab source, **not** a qualification run against the exact current committed verifier/test files.
- Authorization boundary remains explicit: the signed `tenant_access=true` assertion is trusted as a Gateway attestation. This verifier does not independently query IdP membership, role/scope entitlements, resource ownership, or tenant membership; those must be enforced by the trusted Gateway and/or a separately qualified authorization layer. No PostgreSQL, real IdP, GitHub Actions, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Internal principal service-key and tenant-header spoof regressions

- Added eight cases to `tests/test_gateway_auth_extra.py`:
  - Missing, empty and incorrect internal service keys return 401.
  - An unconfigured internal service key fails closed with 503.
  - A valid service key without a signed Gateway assertion returns 401.
  - A caller-supplied `X-Tenant-ID` cannot override the tenant in the verified signed assertion.
  - Assertions bound to a different HTTP method or path return 401.
  Commit: `645e0b68307d94aaaf95c66c817e5975b07d7974`.
- The tenant-header test initially failed because its helper generated a fixed historical assertion timestamp while `internal_principal` correctly uses the live clock. Fixed the test by freezing `app.security.time.time` at the helper's test timestamp. Commit: `a59ce3538d3836f38061f0c0c12516235ba93480`.
- Internal lab: `python -m pytest -q tests/test_gateway_auth_extra.py` => **37 passed in 0.35s** (29 existing + 8 new).
- **Exact-source caveat:** the lab's `app/security.py` Git blob SHA `9272074e061e176e78ea32d42198da3d43f82a05` does not match current GitHub source SHA `06f7bd7bb309133823efefd68dddb8d7784d90ca`; local `tests/test_gateway_auth_extra.py` SHA `e1d2cfcc21d156fcccaf9a4e0580e58d2f19dbae` also does not match committed SHA `deab17e7145566c3432a962e0338e3dc41da55f5`. The 37-pass result is a local adapted-lab check, **not** exact committed-source qualification.
- These checks prove the service key alone does not select a tenant and that the signed assertion is request-bound. They do not prove the upstream Gateway actually authenticates actor→tenant membership, resource-level entitlements, replay prevention, or network/mTLS bypass resistance. No PostgreSQL, live IdP, GitHub Actions, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Replay and resource-authorization architecture audit (no unsafe wiring)

- Audited the current branch tree and exact committed sources:
  - `app/gateway_replay.py` implements a shared PostgreSQL digest reservation with atomic `INSERT .. ON CONFLICT DO NOTHING`, explicit commit-before-success and rollback on duplicate/error.
  - `migrations/versions/0002_gateway_replay.py` creates the unique digest primary key and indexed timezone-aware expiry.
  - `tests/test_gateway_replay_postgres.py` contains disposable-loopback-only PostgreSQL schema and 12-way concurrency/later-replay tests.
  - `.github/workflows/ci.yml` defines a dedicated disposable PostgreSQL 16 job that applies migration, downgrades/re-upgrades, verifies DB identity/revision/table, then runs those integration tests.
- The current safety guard `tests/test_gateway_replay_rollout_hold.py` deliberately asserts that neither `app/security.py` nor `app/main.py` imports/calls replay consumption. This is intentional: replay helper/migration are staged, but runtime authentication must remain unwired until the dedicated PostgreSQL qualification and Gateway owner approval are complete. **No GitHub Actions job was triggered in this cycle**, and no PostgreSQL integration pass is claimed.
- Resource authorization review:
  - `tests/test_gateway_resource_acl_contract.py` checks selected route source for tenant context derived from `Principal`, tenant-scoped list predicates, and payload-tenant rejection.
  - `tests/test_resource_list_http_tenant_isolation.py` exercises the real list routes with signed assertions and an in-memory SQL spy, demonstrating tenant and resource-ID predicates while ignoring forged headers. It is explicitly not PostgreSQL/RLS/IdP proof.
  - `app/security.py` verifies the signed assertion but does not independently query actor membership, roles/scopes or resource ownership. The trusted Gateway ACL and network/mTLS boundary remain external release dependencies.
- **No test count added:** this cycle was a source/architecture audit only; no new code or tests were executed. The previous 37-pass adapted-lab result remains non-exact-source and must not be represented as current branch qualification.
- Next safe actions: run the existing replay suite only against the explicitly disposable PostgreSQL 16 fixture (internal lab preferred); separately obtain Gateway owner approval and a verifiable actor→tenant→resource contract before wiring replay into `internal_principal`. Never use a process-local replay cache. No production/staging DB, no merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — GitHub Actions retry completed but failed before runner execution

- Re-ran failed jobs for Python checks run `43438200263` (attempt 2). It completed with **failure** again; jobs `test`, `frontend`, and `gateway-replay-postgres` all failed.
- Queried the exact attempt-2 jobs endpoint: all three jobs have empty `steps`, `runner_id=0`, empty runner name/group, and start/finish timestamps within approximately two seconds. This is consistent with a failure before normal runner/step execution; it is **not evidence of a code/test assertion failure**.
- The previous deployment-contract run `43438200264` (attempt 1) also failed across its six jobs. Its logs could not be retrieved through the connected GitHub log endpoint (GitHub returned BlobNotFound/404). Therefore the precise root cause is **unavailable**; do not attribute it to code, runner capacity, billing, or permissions without annotations/logs.
- The rerun is not a qualification pass. No PostgreSQL integration execution is confirmed; no step-level evidence was available. Keep replay unwired and **HOLD / NO_GO**. No merge, deploy or LIVE.

### 2026-11-13 — Database-free unit qualification for staged replay helper

- Added `tests/test_gateway_replay_unit.py` (commit `2cb5bf3fa5bab5e4b41ca8ad33caa44b8c9179aa`) with nine cases:
  - issuer + JTI are hashed into a 64-character digest and expiry is bound as UTC;
  - successful reservation commits before returning `True`;
  - duplicate reservation rolls back and returns `False`;
  - commit failure rolls back and propagates (no success);
  - empty issuer, malformed/short JTI, boolean expiry and non-positive expiry fail before database I/O.
- Internal Python lab: **9 passed in 0.24s**, using async mocks and a local transcription of the current `app/gateway_replay.py` implementation. Local helper blob SHA **fddd6371b7be1b18e81a60db572e94151a8e60ef** does **not** equal GitHub blob SHA **6f3407a9ff66d4c29d7ecf3b78af75df40670473**; therefore this is a focused contract check, not exact-source execution.
- No PostgreSQL server or real DB concurrency was exercised. The 12-way PostgreSQL test remains unrun; replay remains deliberately unwired in `app/security.py` and `app/main.py`. No GitHub Actions rerun, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Replay helper exact-source unit qualification and test defect corrected

- Reconstructed the committed replay helper and committed unit test file byte-for-byte in `/mnt/data/gamma_replay_exact`; Git blob hashes match the branch:
  - `app/gateway_replay.py`: **6f3407a9ff66d4c29d7ecf3b78af75df40670473**
  - `tests/test_gateway_replay_unit.py`: **02166f7350636798d54d949f870f9d03b22dd1ae**
- Exact-source run: `python -m pytest -q tests/test_gateway_replay_unit.py` => **11 passed in 0.28s**.
- Added two regression tests:
  - Database `execute` failure rolls back and propagates without commit.
  - Same JTI under different issuers yields different SHA-256 replay keys and verifies the exact issuer-NUL-JTI digest.
  Commits: `73aee1a6bce49377fff7446439be875608e3f5aa`, then digest-test correction `e8990b7ebd1e6a167c822bda6d562b18cccc3ca7`.
- Corrected an actual defect in the earlier invalid-JTI test: it had used the two literal characters backslash+n, not a newline/control character, so it did not exercise the rejection path. The test now constructs a real LF using `chr(10)`. Commit: `677413c0e4d469f075bd98f44a5aad9a1ace6a08`. Exact-source suite now passes all 11 cases.
- This qualifies helper unit behavior only. It does **not** qualify PostgreSQL locking/concurrency, migration round-trip, expiry cleanup, multi-process behavior, or runtime wiring. No PostgreSQL server/asyncpg/Docker in this lab. Replay remains deliberately unwired; no Actions rerun, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Replay migration source contract added to exact-source lab

- Materialized the committed migration and migration contract test byte-for-byte into `/mnt/data/gamma_replay_exact`; Git blob hashes match:
  - `migrations/versions/0002_gateway_replay.py`: **4bf3158e8ed1e45844774b80295ee79ffe49b02b**
  - `tests/test_gateway_replay_migration_contract.py`: **71e6837a3926362aae841247ed4ea2953562c120**
- Re-ran both exact-source suites together: `python -m pytest -q tests/test_gateway_replay_unit.py tests/test_gateway_replay_migration_contract.py` => **15 passed in 0.30s** (11 replay-helper unit tests + 4 static migration-contract tests).
- This confirms source-level revision chaining, digest primary key, timezone-aware non-null expiry, non-unique expiry index, and scoped downgrade ordering. It does not execute Alembic against PostgreSQL or prove actual database schema/locking/concurrency.
- Runtime replay remains intentionally unwired. No PostgreSQL instance/asyncpg/Docker is available in the internal lab. No GitHub Actions, merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Exact-source replay unit suite rerun; PostgreSQL integration remains skipped

- Re-fetched current branch files. Materialized exact GitHub blobs into the internal Python lab and confirmed byte-level Git blob matches:
  - `app/gateway_replay.py`: **6f3407a9ff66d4c29d7ecf3b78af75df40670473**
  - `tests/test_gateway_replay_unit.py`: **02166f7350636798d54d949f870f9d03b22dd1ae**
- Ran the exact committed unit test file against the exact committed helper: **11 passed in 0.22s**. This is the first exact-source unit qualification for this helper in this cycle.
- Reconstructed the PostgreSQL integration test file in the lab from the fetched source, but its local blob SHA **350045d70fb41ec20d00bf80f3eadaca5ba51d04** does not match GitHub blob **25b508661c7e2eeaa544c10edaa7ada4cc646066**. That local adapted test run returned **5 passed, 3 skipped in 0.26s**: the five safety/URL contract cases ran; the three database-backed fixture cases were skipped because no disposable PostgreSQL URL was configured. **No live PostgreSQL schema, 12-way concurrency, cross-session replay, or migration round-trip was exercised.**
- Replay remains deliberately unwired from authentication. No GitHub Actions rerun, no staging/production DB, no merge, deploy or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Exact-source replay unit + migration contract re-run

- Re-fetched current branch sources and reconstructed exact Git blobs in the internal lab:
  - `app/gateway_replay.py`: **6f3407a9ff66d4c29d7ecf3b78af75df40670473**
  - `tests/test_gateway_replay_unit.py`: **02166f7350636798d54d949f870f9d03b22dd1ae**
  - `migrations/versions/0002_gateway_replay.py`: **4bf3158e8ed1e45844774b80295ee79ffe49b02b**
  - `tests/test_gateway_replay_migration_contract.py`: **71e6837a3926362aae841247ed4ea2953562c120**
- Executed the exact unit + migration source-contract files together: **15 passed in 0.34s**. These are DB-free unit/static checks only; migration upgrade/downgrade has not been applied to PostgreSQL.
- Re-ran the opt-in PostgreSQL integration contract previously: **5 passed, 3 skipped**. The three DB-dependent tests skipped because this environment has no PostgreSQL server/client, Docker/Podman, or `asyncpg` driver. Verified again: no `postgres`, `initdb`, `pg_ctl`, `psql`, Docker or Podman executable is available. Do not claim real PostgreSQL qualification or concurrency coverage.
- The current CI workflow already contains a disposable PostgreSQL 16 service job and explicit DB-name/write-acknowledgement guards, but its prior GitHub Actions attempt failed before runner steps; no successful CI PostgreSQL job has been observed. Do not retry Actions automatically in this cycle.
- The replay helper remains deliberately unwired from `app/security.py` and `app/main.py`. No code-path activation, merge, deploy, staging/production DB write, or LIVE. **HOLD / NO_GO**.

### 2026-11-13 — Replay transaction ordering and JTI boundary tests

- Added seven regression cases to `tests/test_gateway_replay_unit.py`: ordered insert-before-commit, conflict rollback-without-commit, distinct JTI digest separation under one issuer, and four noncanonical JTI rejection cases (129 characters, NUL, DEL, non-ASCII). Commit `e35cf925801c6851fba65036fc57414c8037e688`.
- Internal lab `/mnt/data/gamma_replay_current`: verified the new test file Git blob SHA `a9f6035f44faeed9723a473b6c5797772a2f7c57` matches GitHub, and ran `python -m pytest -q tests/test_gateway_replay_unit.py tests/test_gateway_replay_migration_contract.py`: **22 passed in 0.31s** (18 replay unit + 4 migration contract). Prior lab verified the replay helper and migration source blobs against GitHub.
- This does not establish actual PostgreSQL concurrency or migration upgrade/downgrade. Internal runtime lacks PostgreSQL binaries, Docker/Podman, and asyncpg; no external or production DB was accessed. No GitHub Actions rerun. Replay remains unwired; no merge, deploy or LIVE. **HOLD / NO_GO**.
