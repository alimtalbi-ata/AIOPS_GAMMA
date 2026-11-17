# ChatGPT lab — runner execution contract (2026-11-12)

**Scope:** local reconstructed runner source, mocked pytest, no network or real database.

## Executed

Command: `cd /mnt/data/gamma_lab && python -m pytest -q tests/test_bounded_lab_runner.py tests/test_bounded_lab_execution_contract.py`

Environment: disposable ChatGPT container, Python 3.13.5, pytest 9.0.2.

**Observed:** `13 passed in 5.55s`.

The original eight synthetic-checkout preflight tests were joined by five tests of the runner's execution contract:

- Three parametrized subprocess outcomes: `0` maps to `pass`; `1` and `2` map to `fail`, preserving exact exit codes in JSON.
- Unsafe report location prevents launching pytest.
- Inherited `DATABASE_URL`, even empty, prevents launching pytest.

All subprocess calls for the five new tests were mocked. No real GAMMA application suite ran. The local directory contains manually reconstructed files, not an authenticated Git checkout. The new tests were then added to the private repository via GitHub connector; this local result does **not** prove exact-head GitHub CI passes.

## Pending

1. Obtain the complete repository at a verified commit SHA inside an approved disposable environment.
2. Execute `python -m pytest -q tests/test_bounded_lab_runner.py tests/test_bounded_lab_execution_contract.py` on that checkout.
3. Execute `python scripts/run_bounded_lab.py --check-only` and then the fixed allowlist; record command, environment, exit status and test output.
4. Separately qualify disposable PostgreSQL 16, frontend, Docker, Helm, and real IdP/tenant/resource ACL. GitHub Actions pre-step failures remain unresolved.

HOLD / NO_GO: no merge, deployment, LIVE or production-host operation.
