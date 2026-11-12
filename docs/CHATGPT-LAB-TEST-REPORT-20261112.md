# ChatGPT isolated lab — bounded test execution (2026-11-12)

**Scope:** user-requested temporary alternative to blocked GitHub-hosted runners. **HOLD / NO_GO unchanged.**

## Execution

A disposable Python 3.13.5 environment inside this ChatGPT session was used to execute a **small, manually reconstructed subset** of GAMMA source. GitHub's private repository could not be cloned directly in this lab (network DNS access to `github.com` unavailable). The `app/reused/upstream.py` and `tests/test_canonical_acl_hard_hold_static.py` contents were copied from GitHub connector file reads on branch `feat/observability-foundation` (source blob `8aa5ba94ef422e35ab86863c4319ea422b880e46`, test blob `ce112638225bb9f779b685386874949b3f7cd009`). A minimal `app/settings.py` stub was supplied by the lab, **not from the repository**.

Command: `python -m pytest -q tests/test_canonical_acl_hard_hold_static.py tests/test_canonical_lab.py`

Result: **5 passed in 0.23s**. One existing static AST regression test passed; four lab-only parameterized/runtime checks passed (Core/Evidence/Twin deny 503 and unknown resource 404). The lab-only tests were not committed to the repository. No network call was needed for canonical fetch.

**Interpretation:** narrow evidence that the isolated fail-closed canonical adapter behaves as expected with a stub configuration. **NOT** evidence that the full GAMMA repository tests pass, the real FastAPI route works, PostgreSQL 16 isolation works, GitHub CI is repaired, or a real IdP/tenant ACL is qualified. Python 3.13.5 differs from GitHub workflow Python 3.12.

## Migration approach

- Keep GitHub Actions YAML intact: this ChatGPT session cannot be registered as a persistent GitHub Actions runner or host an always-on CI replacement.
- Use isolated ChatGPT labs for narrowly reproducible tests and document exact code provenance, environment, command and outcome. Never promote lab-only tests to release gates.
- Continue GitHub Actions runner/billing/organization-policy triage documented in `docs/GITHUB-ACTIONS-PRESTEP-TRIAGE-20261112.md`. All nine previous GitHub jobs returned `steps:null`; three log fetches returned `404 BlobNotFound`, with no proven root cause.
- For full tests, a **separately provisioned, explicitly approved, persistent runner** with access to private repository contents and disposable PostgreSQL 16 is required. Do not use the Debian production host or touch its Docker data root.

No merge, deployment, production write, replay-auth activation, or LIVE action was performed.
