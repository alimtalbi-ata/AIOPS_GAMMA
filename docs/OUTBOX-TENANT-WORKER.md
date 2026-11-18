# Tenant-bound Outbox worker — proposed security contract

Status: HOLD / NO_GO LIVE. No role provisioning or dispatch authorized.

- One dedicated login per authorized tenant, separate from API and migration roles.
- DBA-managed mapping from session_user to tenant UUID; workers cannot modify it.
- Restrictive RLS policy for worker roles must enforce this mapping on both USING and WITH CHECK, independently of caller-controlled app.tenant_id.
- Grant SELECT on Outbox and UPDATE only on delivery-state columns; no INSERT, DELETE, other tenant tables, replay-table access, ownership or BYPASSRLS.
- Verify effective privileges, inherited role memberships and SET ROLE boundaries before rollout.
- claim_statement is an offline query builder, not an authorization decision.
- Receiver identity and tenant routing must be independently qualified. At-least-once delivery requires receiver deduplication by event ID and tenant.
- Disposable PostgreSQL tests must prove two workers cannot claim the same locked row, cannot access other tenants even by changing the GUC, and cannot alter payload or tenant ownership.
- Use mock HTTP transport only for qualification; do not enable existing relay entrypoint.

No integration migration or role creation has been performed.
