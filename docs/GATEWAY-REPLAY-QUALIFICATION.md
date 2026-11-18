# Gateway assertion replay protection — qualification note

## Runtime behavior

The FastAPI `internal_principal` dependency now verifies the signed, request-bound assertion and then reserves the pair `(issuer, jti)` in the shared PostgreSQL table `gateway_assertion_replay` before returning a principal to a protected route.

- Reservation is an atomic `INSERT ... ON CONFLICT DO NOTHING RETURNING` against the unique digest primary key.
- The reservation is committed before protected handler code can execute.
- A duplicate JTI is rejected with HTTP 401.
- A database or commit failure is rejected with HTTP 503; access is not granted.
- A dedicated short-lived SQLAlchemy session is used, separate from any route business transaction.
- The database migration `0002_gateway_replay` must be applied before protected gateway-authenticated endpoints can succeed.
- No process-local cache is used; multiple application workers share the same PostgreSQL uniqueness constraint.

## Important operational consequences

This is strict one-time assertion consumption, not an idempotency mechanism. A client retry with the same signed assertion is rejected even if the first request failed later in its handler. The trusted gateway must mint a fresh JTI for every HTTP attempt. The gateway must authenticate the actor and authorize actor→tenant→resource before signing; GAMMA's signature check is not a substitute for that ACL.

The table needs retention/cleanup of expired rows. Cleanup must never delete unexpired entries and should be bounded/batched. No automatic cleanup job is enabled by this change.

## Qualification still required

- Apply and verify migration 0002 against disposable PostgreSQL 16.
- Run parallel duplicate-reservation tests using independent DB sessions/processes; exactly one request may reserve a given issuer/JTI.
- Verify commit failure, database outage, expired-row cleanup and restart/multi-worker behavior.
- Verify same-token replay, route/method mismatch, expiry, and fresh-JTI retry through the ASGI app.
- Verify gateway strips browser-supplied identity headers and enforces ACL independently.
- Capture real CI step logs on the exact reviewed PR HEAD.

Until these checks pass, PR #1 remains Draft / HOLD / NO_GO. No LIVE reads, mutation, merge or deployment is authorized.

## Tests added

`tests/test_gateway_replay.py` now covers atomic INSERT conflict handling, commit-before-return, duplicate rollback, commit-failure rollback, and an opt-in five-session PostgreSQL race. The race test requires `GAMMA_TEST_DATABASE_URL` pointing only to a disposable PostgreSQL database; without it, pytest reports the integration case as skipped. The test creates the replay table if absent and removes its unique test digest in a finally block. It does not apply Alembic migration 0002 or qualify migration upgrade/downgrade.

The current code and tests have not yet been executed in CI. Do not interpret test presence as test success.


## Expired reservation cleanup

`app.gateway_replay.purge_expired_assertions` provides one bounded maintenance batch:
- selects only rows with `expires_at < database NOW() - grace_seconds`;
- defaults to a 500-row batch and 120-second grace window;
- enforces batch size 1..10,000 and grace 60..86,400 seconds;
- orders oldest expiry first and uses `FOR UPDATE SKIP LOCKED` so multiple maintenance workers do not block on the same rows;
- commits the deletion batch; database/cancellation errors roll back and propagate;
- is deliberately not called from the request authentication path.

The grace window is a conservative clock-skew allowance, not a replacement for synchronized clocks. Cleanup scheduling, monitoring, and retention alerting are not deployed by this helper. The helper has no effect until a separately authorized maintenance job invokes it.

Unit tests cover SQL guardrails, configured bounds, successful bounded deletion, and rollback on database failure. A live PostgreSQL race between cleanup and valid authentication has not yet been run. Keep the grace window greater than the maximum accepted assertion lifetime plus expected clock skew before enabling a scheduled cleaner.


## PostgreSQL cleanup integration fixture

An opt-in integration test now inserts three expired reservations and one future-expiring reservation into the migration-created table. It invokes cleanup with a batch limit of two, verifies exactly two expired rows are removed while the live row remains, invokes a second batch to remove the final expired row, and verifies the live reservation still exists. The fixture refuses to create a substitute table: migration 0002 must already be applied. It cleans only its deterministic test digests in a `finally` block.

This test requires `GAMMA_TEST_DATABASE_URL` and has not yet been executed against PostgreSQL in CI. It verifies bounded batches and live-row preservation, but does not yet simulate a lock-held cleanup/authentication race or exercise Alembic downgrade/upgrade.


## Concurrent cleanup and authentication integration test

`tests/test_gateway_replay.py::test_two_postgres_cleanup_workers_race_with_fresh_gateway_authentication` runs two independent cleanup sessions and a fresh assertion-consumption session concurrently with `asyncio.gather`. Four expired rows are seeded; each cleanup worker has a batch limit of two. The test requires the combined deletion count to equal four, the new JTI reservation to be accepted, and its digest to remain in the table. The fixture requires Alembic migration 0002 and removes only its deterministic digests in a `finally` block.

This is an opt-in concurrency integration test, not evidence of a successful race run. It requires `GAMMA_TEST_DATABASE_URL` pointing to a disposable PostgreSQL database with migration 0002 applied. It does not hold an explicit row lock to force a particular interleaving, nor does it replace multi-process/container qualification.


## Actor-to-resource authorization checks

The signed principal defaults both resource-grant collections to empty. Log search requires an exact service-name match in `log_service_grants`; evidence read/write requires an exact incident ID match in `evidence_incident_grants`. Wildcards, duplicate grants, path-like incident grants and malformed service names are rejected while verifying the assertion. Tenant ID is always taken from the verified principal, never from request payload or caller-selected tenant headers.

New tests:
- `tests/test_gateway_assertion.py`: least-privilege empty defaults, exact grants, malformed/wildcard/duplicate grant rejection.
- `tests/test_resource_acl.py`: route-boundary denial for ungranted log service and incident evidence, and exact-grant positive-path checks.

These tests do not prove that the upstream gateway actually performs actor→tenant membership lookup, strips spoofed identity headers, or derives grants from a current authoritative ACL. Those remain gateway deployment/integration requirements. No database row-level security policy is asserted here.


## Tenant persistence isolation regression checks

New `tests/test_tenant_isolation.py` checks:
- binding writes derive `tenant_id` only from the verified Principal; request schemas reject an injected tenant field;
- binding reads include a tenant predicate and bind the verified tenant UUID;
- evidence reads include both tenant and incident predicates, and bind both values;
- evidence access without the exact incident grant is denied before any DB query.

Current route review:
- Inbox deduplication reads include `tenant_id`, and writes use the principal tenant.
- Outbox writes inherit the principal tenant; there is currently no tenant-facing outbox read route in the inspected API.
- Evidence writes use principal tenant and exact incident grant; reads filter tenant + incident.
- ServiceBinding writes and reads use principal tenant.

Important remaining boundary: these are application-level predicates and route tests, not PostgreSQL Row-Level Security. The current migrations do not create RLS policies, and the DB connection does not establish a transaction-local tenant context. A future RLS rollout needs explicit policy design, migration/role testing, and a non-owner application DB role; do not claim database-enforced isolation today.


## PostgreSQL RLS enforcement (migration 0003)

Migration `0003_tenant_rls` enables and forces RLS on `integration_inbox`, `integration_outbox`, `telemetry_service_bindings`, and `investigation_evidence`. Both USING and WITH CHECK compare `tenant_id` with transaction-local `current_setting('app.tenant_id', true)`; absent context yields no visible rows and rejects writes.

Protected API database dependencies now use `get_tenant_session`, which sets the context from the verified Gateway Principal with `set_config(..., true)` (transaction-local). Gateway replay uses its own session and is not tenant-scoped.

**Runtime role requirement:** PostgreSQL superusers and roles with BYPASSRLS bypass row policies. The API container therefore uses the dedicated `gamma_app` role, bootstrapped as NOSUPERUSER/NOBYPASSRLS by `postgres/init/01-app-role.sh`. The migration/bootstrap connection remains `aiops`; it owns schema objects. The migration grants DML on tenant tables and replay-table access to gamma_app. Do not point the API's DATABASE_URL at the bootstrap/superuser role.

Compose initialization scripts run only when the PostgreSQL data directory is first initialized. For an existing volume, an administrator must create the restricted role and grant the required privileges before applying migration 0003; do not delete production volumes to force initialization.

New opt-in integration test `test_postgres_rls_denies_cross_tenant_reads_and_writes` requires `GAMMA_TEST_DATABASE_URL` using gamma_app and schema at revision `0003_tenant_rls`. It asserts the role is neither superuser nor BYPASSRLS, verifies tenant A cannot read tenant B's row, and verifies a forged tenant B write under tenant A context is rejected. It has not yet been run against PostgreSQL in CI. Review and validate the bootstrap script and migration on a disposable PostgreSQL 16 instance before rollout.


### RLS rollout caveats and worker boundary

The earlier statement above that no RLS policies exist is historical and is superseded by migration 0003. All tenant-facing API handlers that use Inbox, Outbox, ServiceBinding or Evidence now obtain their session through the verified-principal dependency, which applies the transaction-local tenant setting. Do not add tenant-owned DB access using the unscoped `get_session` dependency.

The existing outbox relay is a background worker and does not have a verified request Principal. Under forced RLS, an unscoped relay session will see no tenant rows. This is intentionally fail-closed; the relay must not be switched to the bootstrap/superuser role. Before enabling the relay, design a separate narrowly scoped worker model (for example, per-tenant claims with audited tenant context) and add tests. The same rule applies to future background workers.

The API container's restricted role is created only on first initialization of a fresh Postgres volume. Existing deployments require a controlled administrative role-bootstrap and grant procedure; never drop or recreate a data volume as a shortcut. Verify the role has neither SUPERUSER nor BYPASSRLS and does not own tenant tables before rollout.


### RLS correction batch

Relay startup is explicitly disabled until a tenant-aware worker is qualified; Compose no longer supplies bootstrap credentials to the relay. Migration 0003 grants only named tables, not future-table default privileges. Inbox duplicate recovery restores the verified tenant context after rollback. The integration test checks forced RLS via pg_class rather than requiring access to alembic_version, and expects PostgreSQL SQLSTATE 42501 for the denied insert. These changes remain unexecuted against PostgreSQL. A custom tenant GUC is defense against omitted predicates, not against arbitrary SQL execution by a compromised runtime role.
