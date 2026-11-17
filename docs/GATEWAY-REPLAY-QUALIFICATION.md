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
