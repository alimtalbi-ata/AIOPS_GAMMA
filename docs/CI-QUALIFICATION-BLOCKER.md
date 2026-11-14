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
