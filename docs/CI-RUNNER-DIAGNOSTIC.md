# GitHub Actions runner diagnostic — 2026-11-10

## Observed evidence

Branch: `feat/observability-foundation`; PR #1 (draft).
Observed commit: `a064cedc01c67793198195a99a3b2bfbf5f9d833`.

- `Python checks`, run [42887635913](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/42887635913): completed / failure.
- `Deployment contract (static + runtime smoke)`, run [42887635129](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/42887635129): completed / failure.
- Both runs were created at 19:40:37 UTC and marked completed by 19:40:40 UTC.
- Python jobs `frontend` and `test` both report `steps: []`, `runner_name: ""`, and `labels: ["ubuntu-latest"]` in the GitHub REST jobs response.
- Deployment contract jobs `ui-image`, `single-directory-runtime`, `api-postgres-runtime`, `helm`, `compose`, and `postgres-nonroot-experiment` also report failure.

## Interpretation

This is consistent with jobs failing before runner execution, but **does not prove** a billing, policy, quota, or runner-availability root cause. There is no trustworthy evidence yet that `pytest`, `npm`, Docker, or Helm actually executed and failed.

## Operator checks (GitHub UI)

1. Open each linked run and inspect its top-level error banner and job annotations. Record the exact message.
2. Check repository Settings > Actions > General for whether Actions and GitHub-hosted runners are allowed; check organization-level restrictions if applicable.
3. Check Actions usage/billing limits and any account spending or payment holds, if the UI indicates a quota/billing issue.
4. Confirm runner availability for `ubuntu-latest` and whether a workflow approval is pending.
5. Once runner execution is restored, rerun the existing checks and retain complete job logs before diagnosing code-level failures.

## Release gate

CI is **not green**. Offline tests and real OpenSearch staging tenant isolation remain **unqualified** until successfully executed and recorded. Do not merge or deploy based on the existence of these workflow runs.


## Retry after replay migration contract guard — 2026-11-11

Head commit: `966a1036440e0c72f6fce926019b7441d8a76f5b`.

- Python checks, run [43106934410](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43106934410): completed / failure. Jobs `frontend` and `test` both report `steps: null`.
- Deployment contract, run [43106934326](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43106934326): completed / failure after rerun. All six jobs report `steps: null`.
- A further rerun was accepted for both workflows. The deployment run again completed with all jobs failed and no steps. Python checks also completed with both jobs failed and no steps.
- Job log retrieval for Python `test` (job `130814615482`) and deployment `compose` (job `130814654213`) returned GitHub Actions artifact `BlobNotFound` / HTTP 404.

Interpretation remains deliberately limited: the API response contains no runner-step evidence, and the log blobs are unavailable. This does **not** establish a code-level failure or a specific billing, policy, quota, or runner-capacity cause. Do not claim tests, Docker, Helm, or frontend build ran.

## Release gate

CI remains **not green**. The new replay migration AST guard, full-app HTTP boundary suite, actual PostgreSQL migration/concurrency, Gateway actor→tenant/resource ACL, and live replay wiring are not qualified. Keep replay helper unwired and retain **HOLD / NO_GO** for merge, deployment, and LIVE.


## Retry after replay helper source guard — 2026-11-11

Head commit: `0e4e09205482133cd1c73da172cd04e62054a318`.

- Python checks run [43108299474](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43108299474): completed / failure; both `frontend` and `test` jobs report `steps: null`.
- Deployment contract run [43108298991](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43108298991): completed / failure; all six jobs report `steps: null`.

No step/log evidence is available from these job responses. Do not infer that any workflow command executed. CI remains not green and cannot qualify the newly added source-contract guard.


## Dedicated disposable PostgreSQL replay job added — 2026-11-11

Commit: `040171999c28a289103013e1e8662081a7162d67`.

The Python workflow now defines `gateway-replay-postgres` with an ephemeral PostgreSQL 16 service and a database named `gamma_replay_test`. It installs the project test dependencies, applies `alembic upgrade head`, then runs only `tests/test_gateway_replay_postgres.py` with the explicit disposable-write acknowledgement. The test module additionally requires loopback PostgreSQL, the `*_replay_test` database suffix, and migration revision `0002_gateway_replay`; it tests two-session concurrent uniqueness and committed replay rejection, and deletes only its own digest rows.

GitHub run [43108661421](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43108661421) for this commit completed failure. Its `frontend`, `test`, and new `gateway-replay-postgres` jobs all report `steps: null`. Therefore the PostgreSQL service, Alembic migration, and pytest integration command have **not been evidenced as executed**. This job addition is prepared, not qualified. CI remains not green; no merge/deploy/LIVE.
