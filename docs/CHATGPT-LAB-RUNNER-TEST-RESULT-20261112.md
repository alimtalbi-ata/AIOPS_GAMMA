# ChatGPT isolated lab — bounded runner safety checks (2026-11-12)

**Status:** 8/8 local tests passed, **limited to a reconstructed source subset**. HOLD / NO_GO.

## Execution evidence

- Environment: disposable ChatGPT container, Python 3.13.5, pytest 9.0.2.
- Local directory: `/mnt/data/gamma_lab` (not a GitHub checkout).
- Source: manually reproduced contents of `scripts/run_bounded_lab.py` and `tests/test_bounded_lab_runner.py` from the current PR branch, with the previously existing limited canonical adapter lab files. No direct private repository clone or artifact was available.
- Command: `cd /mnt/data/gamma_lab && python -m pytest -q tests/test_bounded_lab_runner.py`
- Observed output: `........ [100%]` and `8 passed in 5.53s`.

The eight cases exercise:
1. Synthetic complete-checkout `--check-only` acceptance without invoking pytest.
2. Incomplete-checkout rejection.
3. Three inherited database/replay environment variable refusals, including empty values.
4. Two report paths inside checkout rejected.
5. Report path outside checkout accepted without creating it in check-only mode.

**Not executed:** full ten-file GAMMA application test allowlist, full repository CI, real PostgreSQL 16, frontend, Docker, Helm, IdP/ACL or production. A manually reproduced subset cannot substitute for an exact checked-out Git commit. No external services or LIVE resources were contacted.

**Next step:** obtain an actual full private repository checkout inside an explicitly approved disposable test environment, verify the commit SHA, then run `python scripts/run_bounded_lab.py --check-only` and the allowlisted tests. Preserve GitHub Actions for independent CI once runner provisioning is fixed.
