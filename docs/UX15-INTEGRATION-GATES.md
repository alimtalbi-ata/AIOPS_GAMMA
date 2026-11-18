# UX15 — Integration qualification hold

Reviewed PR #10 head `a12b8516edb51d155e237a34aac3ca7df0eeebff`, base `3b07ecebf1aea9146314535940bb954add50f2d1`, generated merge `7be26f8e8251e91d5aa0c873db9e704a0d8468d4`.

## Findings
Head security.py does not wire replay reservation or business permissions. The generated merge does both. Do not backport test fixtures in isolation or remove these controls to obtain green CI.

Integrated RLS run 44284103771: 23 passed, 3 failed. Job 134732165131 identifies missing bindings:write, bindings:read and evidence:read permissions in direct-handler fixtures. Add explicit least-privilege permissions after synchronization; add negative tests without permission and preserve tenant/resource predicates.

Integrated E2E job 134732182621 fails on missing gamma_app at migration time. Provision a restricted runtime role and separate migration administrator; qualify full migration head, tenant transaction context and replay independently. Do not downgrade migrations or grant BYPASSRLS to make the integrated tests pass.

## Required sequence
1. Merge the current foundation into the UX branch locally, without merging PR #10 into foundation. Review conflicts, then push the UX branch.
2. Adapt smoke tests to the real replay boundary; retain import-without-DB and unsigned request denial tests. Use real disposable PostgreSQL for positive full-stack replay verification.
3. Update business permission fixtures and explicit negative cases. Verify gateway key configuration and resource grants.
4. Qualify full-head E2E, RLS, Python and all deployment jobs on the same integrated SHA. The table-scoped restore rehearsal is not a complete database restore.
5. Retain draft/release hold until gateway owner, upstream tenant ACL, real telemetry, audit and deployment gates are satisfied.

## Status
NO-GO. No merge or deployment authorized. Connector exposes no direct update-branch action; synchronization requires a Git-capable environment or separately approved integration workflow. This document is a diagnosis, not successful qualification.
