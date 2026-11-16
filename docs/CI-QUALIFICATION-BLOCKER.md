# CI qualification blocker — 2026-11-14

## Latest verified Actions status — 2026-11-16

At HEAD `26e3fb45c1a678880c789955305442d088e08ef9`,
[Python checks run 43948088379](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43948088379)
completed with `failure`. The jobs API reports **zero steps** for all four
failed jobs: `test` (133582959095), `tenant-evidence-postgres-e2e`
(133582959504), `gateway-replay-postgres` (133582959533), and `frontend`
(133582959866). This is a platform/runner qualification blocker, **not** a
pytest or PostgreSQL test result. A repository administrator must inspect
job-level Actions UI diagnostics, runner access, billing and repository Actions
policy; no specific cause is established by the available API evidence.
No successful execution evidence exists for later commits. **HOLD / NO_GO.**

## Latest GitHub Actions evidence — 2026-11-16 (newer run)

At reviewed HEAD `7925e3fa02518cc5ba31e1c97b7c0bc675ce3ce7`,
[Python checks run 43937111594](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43937111594)
completed with `failure`. Its four jobs all completed with `failure`
within approximately two seconds and each exposes **zero steps** in the
GitHub Actions jobs API:

- `tenant-evidence-postgres-e2e` — job `133544499646`
- `gateway-replay-postgres` — job `133544500127`
- `test` — job `133544500274`
- `frontend` — job `133544500277`

The paired deployment-contract run `43937111599` also reports `failure`.
These API results do not establish that a runner executed any checkout,
pytest, frontend build, or PostgreSQL command. An administrator must inspect
the Actions UI job-level annotations, runner availability, billing and policy
settings. Do not assert a specific platform cause without direct evidence.
**HOLD / NO_GO.**

## Latest GitHub Actions evidence — 2026-11-16

At reviewed HEAD `3d8f9b42bfe083f6fed3af50444fd2c0d58be8c9`,
[Python checks run 43934491406](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43934491406)
completed with `failure`. The API reports all four jobs failed:

- `frontend` — job `133535386505`
- `tenant-evidence-postgres-e2e` — job `133535386862`
- `test` — job `133535387153`
- `gateway-replay-postgres` — job `133535387218`

Independent job-step queries returned **zero steps for each job**.
Direct job-log retrieval for all four job IDs also returned **HTTP 404
`BlobNotFound`** on 2026-11-16. The exact platform failure remains
unidentified; this is not evidence that application tests executed.

This does not establish that checkout, tests, or PostgreSQL ever started;
record the GitHub Actions UI runner/platform error before rerunning.
Subsequent commits require qualification at their own exact HEAD.
**HOLD / NO_GO remains unchanged.**

## Observed evidence (not a pytest result)

PR #1 remains Draft / HOLD / NO_GO. At HEAD
`3a0af09e7a466e6c417d383badd7473bcd1a51bb`, GitHub Actions reports:

- Python checks: run `43614796767` — failed jobs `test`,
  `frontend`, `gateway-replay-postgres`.
- Deployment contract: run `43614796774` — failed jobs
  `single-directory-runtime`, `compose`,
  `postgres-nonroot-experiment`, `helm`,
  `api-postgres-runtime`, `ui-image`.
- Job-step queries for `test`, `frontend` and
  `single-directory-runtime` return **zero steps**.
- The Python job log download returns HTTP 404 BlobNotFound.

This evidence does **not** establish that checkout, dependency installation,
Python compilation, pytest, PostgreSQL or any deployment command ran.
Do not classify these failures as application test failures or mark CI green.

## Required next actions (repository administrator / CI operator)

1. Open the two run URLs in the GitHub Actions UI and inspect the run
   summary for runner allocation, billing/usage limits, Actions policy,
   repository permissions and any GitHub incident notice.
2. Verify that GitHub-hosted runners are allowed and available for this
   private repository; review account/organization Actions spending and
   concurrency settings. Record the exact platform error.
3. Only after the runner issue is resolved, rerun the **same reviewed HEAD**
   and collect actual per-step output. If the HEAD changed, qualify the new
   exact SHA instead.
4. For the Python job, require successful checkout, Python setup,
   `pip install -e '.[test]'`, `compileall` and `python -m pytest -q`.
   Archive the test counts and failures.
5. Separately qualify frontend build, disposable PostgreSQL replay and
   deployment-contract jobs. Never point test DATABASE_URL to a real database.
6. Re-evaluate PR gates only after the independently reviewed
   actor→tenant→resource ACL, tenant-negative tests and all other required
   staging/security checks are demonstrated.

## Local fallback (isolated, no VM)

On an authorized machine with a reviewed checkout and no production secrets:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m compileall -q app tests
python -m pytest -q \
  tests/test_synthetic_incident_usecase.py \
  tests/test_synthetic_rca_usecase.py \
  tests/test_synthetic_impact_usecase.py \
  tests/test_synthetic_end_to_end_usecase.py \
  tests/test_synthetic_runbook_hitl_usecase.py \
  tests/test_synthetic_journey_negative_gates.py \
  tests/test_evidence_normalization.py \
  tests/test_itil_mutable_boundary.py \
  tests/test_topology_preview.py
```

These pure synthetic tests are not substitutes for gateway ACL, staging,
canonical Core/Evidence/Twin, GLPI, signed HITL, PostgreSQL or LIVE qualification.

**Release decision: HOLD / NO_GO. No merge, LIVE action or deployment.**


## Targeted rerun evidence — 2026-11-14

- GitHub accepted a targeted rerun of the Python `test` job on run `43614889197` for commit `056db62d76c4362a98fca4884d240da931dd5293`.
- Replacement job `132507795650` finished `failure`; its job-step endpoint returned an empty array and log retrieval returned `404 BlobNotFound`.
- Therefore the rerun **did not establish a runner or a pytest execution**. Avoid repeated blind reruns until an administrator identifies the run-summary error.
- Tracking issue: https://github.com/alimtalbi-ata/AIOPS_GAMMA/issues/8
- No code-level test failures are proven. PR remains Draft HOLD / NO_GO.


## Latest HEAD qualification check — 2026-11-14

At reviewed HEAD `5b00b71d6248df34552588798e519b58dab2ceb4`:

| Workflow | Run | Outcome |
| --- | --- | --- |
| Python checks | [43618484414](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43618484414) | completed / failure |
| Deployment contract (static + runtime smoke) | [43618484411](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43618484411) | completed / failure |

The job-step endpoint returned **`steps: []`** for these sampled jobs:

- Python `test` — `132518669917`
- Python `gateway-replay-postgres` — `132518670201`
- Deployment `postgres-nonroot-experiment` — `132518670088`

The jobs' failed status alone does **not** prove that tests or database commands ran. No fresh job logs were inspected in this check. The earlier `404 BlobNotFound` observation above pertains to the earlier run and should not be automatically attributed to these new runs.

**Operator evidence needed:** capture the exact GitHub run-summary or runner-allocation error for these run IDs; confirm Actions permissions, billing/usage and runner availability. Do not rerun blindly. Once fixed, qualify the exact reviewed SHA with recorded per-step logs and test counts, using disposable infrastructure only. Canonical ACL issue #2 is an independent blocker.

**PR #1 remains Draft — HOLD / NO_GO.**


## Current HEAD CI observation — 2026-11-14

Reviewed commit `f7bf8913ea21403658762c5e18325cedc9841a63`:

| Workflow | Run | Result |
| --- | --- | --- |
| Python checks | [43622717249](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43622717249) | completed / failure |
| Deployment contract (static + runtime smoke) | [43622717214](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43622717214) | completed / failure |

The Python `test` job (`132531736563`) and Deployment `compose` job (`132531736441`) both returned `steps: []` from the job-step endpoint. The workflow job listings also provided no logs URL for the listed jobs. **No fresh log-download attempt was made**, and the earlier `404 BlobNotFound` result must not be projected onto these runs.

These observations do not demonstrate execution of pytest, compose, PostgreSQL, or any application check. Administrator must inspect the GitHub run summary / runner allocation and Actions billing or permissions, then obtain real step logs for the reviewed SHA. Do not rerun blindly. Independent canonical ACL issue #2 still blocks release.

**Decision unchanged: PR #1 Draft — HOLD / NO_GO; no merge, deploy, LIVE or remediation.**


## CI observation on UC04 reverse-dependency HEAD — 2026-11-14

Reviewed PR commit `1eafd9ab0722d39d3db87aec3dccd4759f0548a7`:

| Workflow | Run | Conclusion |
| --- | --- | --- |
| Python checks | [43629797277](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43629797277) | completed / failure |
| Deployment contract | [43629797288](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43629797288) | completed / failure |

Python `test` job `132553648125` and deployment `compose` job `132553648255` both returned `steps: []`. The job listings returned `logs_url: null` for all sampled workflow jobs. No fresh log-download attempt was made, and the earlier BlobNotFound finding is **not** evidence for these new runs.

**Next operator action:** inspect the run summaries for GitHub-hosted runner allocation, Actions permissions, billing/usage or platform restrictions; record the exact error in [issue #8](https://github.com/alimtalbi-ata/AIOPS_GAMMA/issues/8). Do not blindly rerun. Once repaired, run the **exact reviewed SHA** and retain per-step checkout, install, compileall, pytest, frontend and disposable PostgreSQL evidence. Include `tests/test_topology_preview.py` in the pure Python regression suite. No real database or LIVE access.

**Independent blocker:** canonical actor→tenant→resource ACL [issue #2](https://github.com/alimtalbi-ata/AIOPS_GAMMA/issues/2). PR #1 remains Draft HOLD / NO_GO.


## Follow-up CI observation — 2026-11-14

At PR HEAD `998fdf1a631f30ad328e1ad9d6699eb3c17a56df`:

| Workflow | Run | Outcome | Sampled job |
| --- | --- | --- | --- |
| Python checks | [43630497249](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43630497249) | completed / failure | `test` `132555803705`: `steps: []` |
| Deployment contract | [43630497344](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43630497344) | completed / failure | `compose` `132555804039`: `steps: []` |

All jobs listed for these two runs returned `logs_url: null`. No log download was attempted in this observation; do not infer `BlobNotFound` for these runs. No checkout, pytest, compose or database execution has been demonstrated.

**Administrator handoff:** inspect both run summaries in GitHub's UI; capture the exact pre-step/runner allocation error, Actions policy and usage/billing constraints. Record findings in [issue #8](https://github.com/alimtalbi-ata/AIOPS_GAMMA/issues/8), then obtain per-step evidence for the exact reviewed HEAD after repair. Do not rerun blindly or weaken test gates. Independent ACL [issue #2](https://github.com/alimtalbi-ata/AIOPS_GAMMA/issues/2) remains blocking.

**PR #1 Draft — HOLD / NO_GO.**


## Latest reverse-path test HEAD observation — 2026-11-14

At reviewed PR HEAD `2a975e7724d0450571dff277ff17e683226ba770`:

| Workflow | Run | Outcome | Sampled job |
| --- | --- | --- | --- |
| Python checks | [43630918281](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43630918281) | completed / failure | `test` `132557084360`: `steps: []` |
| Deployment contract | [43630918325](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43630918325) | completed / failure | `compose` `132557084471`: `steps: []` |

All listed jobs in both workflows returned `logs_url: null` and failure. No log download attempted for these runs; do not attribute the older `BlobNotFound` result to them. No test, compilation, Compose, PostgreSQL or deployment execution is evidenced.

**Operator next step:** capture the exact run-summary failure reason, runner assignment, Actions policy/permissions and billing/usage status for these run IDs in [issue #8](https://github.com/alimtalbi-ata/AIOPS_GAMMA/issues/8). Do not blindly rerun. After repair, qualify the **exact reviewed SHA** with real step logs and test counts; the isolated fallback includes `tests/test_topology_preview.py`. Independent ACL [issue #2](https://github.com/alimtalbi-ata/AIOPS_GAMMA/issues/2) still blocks release.

**PR #1 Draft — HOLD / NO_GO.**


## Exact-HEAD CI verification — 2026-11-14 (UC04 witness tests)

At PR commit `de2261bac37783f86f78b4cb283d82cf0c04b127`, GitHub reported:

| Workflow | Run | Outcome |
| --- | --- | --- |
| Python checks | [43633546954](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43633546954) | completed / failure |
| Deployment contract | [43633546928](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43633546928) | completed / failure |

All **nine** listed jobs were completed/failure with `logs_url: null` in the job-list responses. Direct job-step queries returned `steps: []` for Python `test` job `132565289375` and Deployment `compose` job `132565289344`. No job-log download was attempted for these runs; earlier 404 observations do not establish the state of these logs. A combined commit-status query returned no individual legacy statuses, which is **not** evidence of green CI.

**Interpretation:** the available evidence does not prove checkout, compileall, pytest, Compose, PostgreSQL or deployment commands ran. The GitHub administrator must inspect the run summaries and runner allocation / Actions policy / billing constraints, record the exact platform error in [issue #8](https://github.com/alimtalbi-ata/AIOPS_GAMMA/issues/8), and obtain actual per-step logs and test counts for the *then-current exact reviewed HEAD* after repair. No blind rerun, weakened checks, real PostgreSQL or LIVE action. Independent ACL [issue #2](https://github.com/alimtalbi-ata/AIOPS_GAMMA/issues/2) remains blocking. **PR #1 Draft — HOLD / NO_GO.**


## Latest observed HEAD — 2026-11-16 (alert outbox envelope tests)

Reviewed commit: `697f9a1fdaa4b0e04d4d080efa9cb07a49a16473`.

| Workflow | Run | GitHub conclusion |
| --- | --- | --- |
| Python checks | [43917442092](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43917442092) | failure |
| Deployment contract | [43917441961](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43917441961) | failure |

Python checks job IDs: `frontend` 133475289648, `test` 133475289887, `tenant-evidence-postgres-e2e` 133475289893, `gateway-replay-postgres` 133475289909. The job listing exposed no step records for these jobs; check runs have failure conclusions without explanatory summaries. A direct annotations query was unavailable through the connected GitHub API endpoint; **no claim is made that the annotations are empty**. Deployment job steps were not inspected for this checkpoint.

**No evidence of test execution or application assertion failure.** The repository/org administrator must inspect the [Python workflow run](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43917442092) in the GitHub UI, including any pre-run error banner, Actions policies, runner provisioning, and usage/billing, then record the exact error and remediation evidence in [issue #8](https://github.com/alimtalbi-ata/AIOPS_GAMMA/issues/8). Do not blindly rerun or weaken gates. Once resolved, run the then-current reviewed HEAD and archive per-step logs and PG16 results. Independent canonical ACL [issue #2](https://github.com/alimtalbi-ata/AIOPS_GAMMA/issues/2) remains a separate blocker. **Draft PR #1: HOLD / NO_GO.**


## Latest rerun investigation — 2026-11-16

The failed jobs of both runs were explicitly re-run (attempt 2):

- [Python checks run 43959539317](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43959539317)
  — all four jobs failed again: `test`, `gateway-replay-postgres`,
  `tenant-evidence-postgres-e2e`, and `frontend`.
- [Deployment contract run 43959539309](https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/43959539309)
  — all six jobs failed again: `compose`, `ui-image`,
  `postgres-nonroot-experiment`, `single-directory-runtime`,
  `api-postgres-runtime`, and `helm`.

The jobs API still reports zero steps for all ten jobs. Attempts to retrieve
job logs returned `BlobNotFound` (404), so no test output or runner diagnostic
is available. This confirms only that the rerun failed before any visible step;
it does **not** establish a root cause. Repository administrator action is
still required to inspect Actions UI/runner diagnostics and policy. **HOLD / NO_GO.**

