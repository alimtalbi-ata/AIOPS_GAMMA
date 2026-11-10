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
