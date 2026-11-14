# CI qualification blocker — 2026-11-14

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
  tests/test_synthetic_journey_negative_gates.py
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
