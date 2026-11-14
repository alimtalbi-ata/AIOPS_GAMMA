# GitHub Actions pre-step failures — operator triage

**Observed:** 2026-11-12. **Security release status:** HOLD / NO_GO.  
**Repository:** `alimtalbi-ata/AIOPS_GAMMA`  
**Commit:** `15a021285953fa3c613cc2837c03125f550c2c11`

## Direct GitHub API evidence

| Workflow | Run | Result | Jobs |
| --- | --- | --- | --- |
| Python checks | [43191691027](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43191691027) | failure | test, frontend, gateway-replay-postgres |
| Deployment contract | [43191691038](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43191691038) | failure | compose, postgres-nonroot-experiment, ui-image, api-postgres-runtime, helm, single-directory-runtime |

- All **nine** job records returned `conclusion=failure` and `steps=null`.
- Separate `fetch_workflow_job_steps` calls for job IDs `131092333382`, `131092333732`, and `131092333770` returned empty arrays.
- Separate job-log retrievals for the same three IDs returned GitHub API HTTP 404 with Azure `BlobNotFound` (blob does not exist). This is a log-storage/retrieval observation, **not** a proven root cause for the failed jobs.
- The checked workflow files `.github/workflows/ci.yml` and `.github/workflows/deployment-contract.yml` each define `runs-on: ubuntu-latest`, checkout and subsequent executable steps. No workflow step execution is evidenced.
- Similar pre-step failures appeared on preceding commits. Re-running unchanged jobs without a new diagnosis has not provided useful evidence.

## Operator-only triage checklist

1. Open both run links above in GitHub Actions. Inspect the run summary, **Annotations**, the failing job's **Set up job** panel (if present), and any banner shown *before* step execution. Capture the exact message and time, without secrets.
2. In repository **Settings → Actions → General**, verify Actions are enabled, the workflows are allowed, and any organization/enterprise policy permits the selected actions and GitHub-hosted runners. Check whether branch/PR restrictions or approval requirements are shown.
3. Check organization/enterprise **Actions runner availability**, usage limits and **billing/spending limits** for GitHub-hosted runners. Record any service incident or account restriction shown. This is a hypothesis to check, not an established cause.
4. Inspect [GitHub Status](https://www.githubstatus.com/) for an Actions/log-storage incident matching the UTC run timestamps. `BlobNotFound` by itself does not establish a platform outage.
5. If the UI exposes a diagnostic annotation or runner provisioning error, attach the **redacted** exact text to PR #1. If not, raise a GitHub Support ticket with repo, run/job IDs, time, `steps=null`, and the 404 `BlobNotFound` response. Do **not** paste tokens, private URLs, assertion contents, credentials or production logs.
6. Only after the failure mechanism is understood, perform a single controlled retry or a narrowly scoped diagnostic workflow. Require non-empty steps and retained logs before treating it as a valid CI run.
7. When the runner works, execute Python, frontend, disposable PostgreSQL replay/migration, Compose and Helm jobs. Then separately qualify real actor/tenant/resource ACL and cross-tenant PostgreSQL/HTTP tests. CI success alone is not deployment approval.

## Explicitly not concluded

- No proof that Python tests, PostgreSQL, frontend, Compose, Helm or Docker actually started on these runs.
- No proof that `BlobNotFound` **caused** the workflow failures.
- No proof that a source-code change, test fix, runner-version change or workflow YAML edit would resolve them.
- No permission to run against Debian, production PostgreSQL, real tenants or LIVE.

**Next evidence needed:** exact Actions UI pre-step annotation or runner provisioning message, followed by a run showing executed steps and accessible logs.


## Latest exact-head recheck — 2026-11-12, commit 529d97f1417654620c96066b958ec9fabdcdff16

- Python checks: [run 43226459064](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43226459064), `completed/failure`, created 13:21:09Z and updated 13:21:12Z. All three jobs failed with `steps=null`: test `131210783891`, frontend `131210784103`, gateway-replay-postgres `131210783482`. Separate steps API returned `[]` for all three.
- Deployment contract: [run 43226458894](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43226458894), `completed/failure`, created 13:21:09Z and updated 13:21:13Z. Six jobs failed with `steps=null`: postgres-nonroot-experiment, api-postgres-runtime, compose, single-directory-runtime, ui-image and helm.
- The run-level API confirms `event=pull_request`, `run_attempt=1` and the exact head SHA above. These observations do **not** establish the root cause or prove that any `compileall`, pytest, npm, Docker, PostgreSQL or Helm command ran.
- **Operator action needed:** inspect each run's GitHub Actions UI annotations and repository/org Actions runner availability, policies, and billing; capture the actual pre-step error before modifying workflows or retrying. No automatic retry or production operation is authorized.
- Quality P0 fixes and the new CI syntax gate remain unqualified by GitHub Actions. HOLD / NO_GO.


## Exact-head pre-step recheck — 2026-11-14, commit 0a51b1d891066c252d87a88be3b3b54f86c42cc4

- Python checks: [run 43612387057](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43612387057), created `2026-11-14T15:51:07Z`, updated `15:51:10Z`, `run_attempt=1`, completed/failure. Three jobs (`test`, `frontend`, `gateway-replay-postgres`) report failure with **zero steps**.
- Deployment contract: [run 43612386885](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43612386885), created `2026-11-14T15:51:07Z`, updated `15:51:10Z`, `run_attempt=1`, completed/failure. Six jobs (`compose`, `single-directory-runtime`, `postgres-nonroot-experiment`, `api-postgres-runtime`, `helm`, `ui-image`) report failure with **zero steps**.
- Both workflows completed in roughly three seconds. The synchronized pre-step failures are consistent with a shared runner/bootstrap restriction, **not proof of a particular cause**. A job-log retrieval for an earlier `test` job returned HTTP 404 `BlobNotFound`; this is a retrieval observation, not a test result.
- **Operator handoff:** capture the exact GitHub Actions UI banner/annotation for these run links (redact sensitive data); inspect repository/org Actions permissions, hosted-runner availability, billing/usage, and pending approvals. If no annotation is available, provide these run IDs and timestamps to GitHub Support. Do not rerun without a specific diagnostic hypothesis.
- **Release gate:** PR #1 Draft; **HOLD / NO_GO**. No pytest, npm, PostgreSQL, Docker or Helm execution is evidenced on these runs. No merge, deployment, LIVE or canonical reads.
