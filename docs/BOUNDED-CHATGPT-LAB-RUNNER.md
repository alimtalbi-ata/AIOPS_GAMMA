# Running bounded GAMMA tests outside GitHub Actions

The repository now includes `scripts/run_bounded_lab.py`, an opt-in, source-only
test runner for a **real checkout** of this private repository in a disposable
environment (including a ChatGPT lab when the repository files are supplied).

## Prerequisites

- An actual complete checkout of the selected GAMMA commit; do not use a
  manually reconstructed subset or assume GitHub connector content is mounted.
- Python 3.11+ and dependencies installed from the checked-out `pyproject.toml`:
  `python -m pip install -e '.[test]'`.
- A disposable environment **without** real database or staging credentials.
- No Docker, production host, IdP or LIVE connectivity is required.

## Invocation

```bash
python scripts/run_bounded_lab.py --report /tmp/gamma-bounded-lab.json
```

To validate the safety preflight without launching pytest:

```bash
python scripts/run_bounded_lab.py --check-only
python -m pytest -q tests/test_bounded_lab_runner.py
```

The preflight refuses a checkout containing `.env` (automatically loaded by `app/settings.py`), inherited `PYTEST_ADDOPTS`, `PYTEST_PLUGINS`, or `PYTHONPATH`, and even **empty** inherited database/replay variables,
and validates the JSON report destination before any test process starts.
The new unit tests use a synthetic disposable checkout and do not run the
application or contact external services. These commands are **instructions**,
not a claim that the full checkout was executed in this ChatGPT session.

The runner uses a fixed allowlist of eleven existing test files covering canonical
HOLD, actual FastAPI canonical route, signed Gateway assertions, tenant-bound
SQLAlchemy list routes, deny-before-database HTTP authentication, and upstream transport contracts. It deliberately
excludes PostgreSQL replay, migration, staging, Docker and integration suites.
It refuses incomplete checkouts and inherited `DATABASE_URL`,
`GAMMA_REPLAY_TEST_DATABASE_URL`, or `GAMMA_REPLAY_TEST_ALLOW_WRITE`.

The process returns pytest's exit code and emits a JSON report with Python
version, timestamps, exact test paths, command and pass/fail status. The report
path must be outside the checkout to prevent accidental commits. A passing
result is **not** a GitHub Actions check run or production qualification.

## Current status

The script was committed on 2026-11-12; it has **not yet been executed against
a full GAMMA checkout** in ChatGPT. Earlier ChatGPT lab evidence in
`docs/CHATGPT-LAB-TEST-REPORT-20261112.md` covers only five checks on a
manually reconstructed subset and must not be conflated with this runner.

GitHub Actions workflows remain in place. A session-scoped ChatGPT lab cannot
be registered as a persistent hosted runner. Full validation still requires
an approved runner, disposable PostgreSQL 16 and independently qualified real
actor/tenant/resource ACL. HOLD / NO_GO remains in effect.


### Runtime bound

The source-only pytest subprocess has a hard **180-second timeout**. If the
limit is reached, the runner records `result: "timeout"`, `exit_code: 124`
and `timeout_seconds: 180` in its JSON report (when requested), then exits
nonzero. A timeout is never reported as a passing test run. This bounds the
wait, not the capabilities of the environment: use only a disposable isolated
checkout without production connectivity.


### Pytest plugin isolation

The runner sets `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` for the child pytest
process and explicitly enables only `pytest_asyncio.plugin` with
`-p pytest_asyncio.plugin`. This avoids silently importing unrelated
installed pytest entry-point plugins. It does not sandbox Python imports,
repository `conftest.py`, or pytest configuration: execute only in a
throwaway environment with no production network or credentials.

A local ChatGPT Python 3.13.5 / pytest 9.0.2 smoke command
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -p pytest_asyncio.plugin --version`
returned `pytest 9.0.2`; it did **not** execute GAMMA tests.


### Quality audit regression coverage

The fixed source-only allowlist now includes
`tests/test_quality_p0_imports.py`: it parses all application Python files,
imports the corrected schema/outbox/bootstrap modules with engine creation
forbidden, and tests POC bootstrap engine disposal against a fake engine.
No database, webhook, or external network is needed for these cases.
**Presence on the allowlist does not mean the full suite has run.**
