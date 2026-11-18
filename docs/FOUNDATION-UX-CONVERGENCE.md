# Foundation / UX convergence checkpoint — 2026-11-18

Decision: DRAFT / HOLD / NO_GO LIVE. Remote development only.

## Reviewed refs
- Foundation qualification checkpoint: 3f63c828309ad34b67f4f1d552667ad0b0505880 (PR #1).
- User-supplied commit: 99157f5d0c4bd6a1c96de4928df8754f4482ddfc, async malformed Unicode authentication regression tests, not a UI commit.
- UX PR #10: feat/gamma-ui-ux1-dark-console, reviewed head 3b200d43bfda204b8da06b625011e0b462a90a69.
- GitHub compare of foundation checkpoint to UX head: diverged, UX ahead 70 / behind 175; merge base 7779a199a5a23a0436156b57cfbeaef9bcc121cf. Do not treat an isolated UX branch test as integrated qualification.

## Actual CI evidence
Foundation exact checkpoint:
- 44364414820: role preflight, migrated schema audit, negative drift and registry propagation all passed.
- 44364414650: RLS migration round trip and behavioral isolation passed.
- 44364414764: shadow RCA checks passed.
- 44364414762: frontend passed; general Python 2400 passed / 20 failed / 15 skipped; replay setup 7 errors (actual server address not loopback); HTTP tenant E2E setup 6 errors.
- 44364414548: compose static/mocked rootless checks, UI image, API runtime and Helm passed. Single-directory restore failed because the full backup was replayed into a populated schema. Experimental nonroot PostgreSQL failed at host-side private directory stat.

UX exact head:
- 44284724993 (push): frontend, intelligence preview, replay and E2E jobs passed; Python 2348 passed / 1 failed / 1 skipped.
- 44284725011 (push): all six deployment jobs passed.
- 44284738125 (PR): frontend, replay and intelligence preview passed; migration/E2E and general Python failed.
- The UX push tests rely on older schema revision 0002; foundation requires full head 0006, separate admin and restricted gamma_app. Do not replace those protections.

## Cross-agent changes applied to foundation
- dbb48053d6639a4e0959ea86584d8a9331ae952e: adapt UX CI actual-loopback disposable DB setup to foundation, retaining role and migration separation.
- f3c5c35838a64fda7e35b12b291d3e7a5ec821ad: table-scoped restore smoke and read-only sudo stat on hosted CI only. Not full backup/restore qualification.
- e487a10edf4a281f17a684b85205e45c97015e65: pin PG16 tenant policy expression, role, command and permissiveness; allowlist extra worker policies and check their structure; worker predicate semantics still need qualification.
- 6655727c6144796cb0636f825308c890a4848216: add permissive widening and predicate drift negative tests. Exact head workflows queued at observation, no successful result claimed.

## UX review (static)
Dark console, Command Center, Signal Explorer, Incident Workbench, AI Intelligence Center and integration-readiness panels are useful offline contributions. Preserve no browser API transport, synthetic labels, no real upstream connectors or execution. At the supplied 99157f5 snapshot, review inconsistent service health counts (4 healthy / 3 impacted vs KPI 5 / 2), misleading Live topology preview text, mouse-only table rows, focus and Escape handling for drawers, keyboard tabs and visual contrast. Confirm on latest UX head before changing. No browser visual or accessibility pass claimed. Do not treat endpoint status text as real gateway/owner evidence.

## Integration gates
1. Preserve both histories and review differences against exact current heads; no automatic merge, rebase, force push or blind file replacement.
2. Coordinate with UX agent; integrate on a dedicated review branch/PR when authorized. Keep foundation and UX drafts.
3. Qualify full migration head with worker separation and gateway permission/replay checks. Do not downgrade migration or remove RLS for green tests.
4. Require real integrated frontend build, image smoke, browser keyboard/contrast/responsive review, synthetic provenance consistency, no unauthorized network calls.
5. Finish negative policy, owner, worker and ACL checks; wire schema gate only after exact PG16 qualification. Reconcile remaining Python failures, then require exact integrated SHA CI.
6. Canonical ACL issue #2 and gateway/IdP/upstream owner approvals remain independent blockers. No production data, deployment or remediation.
