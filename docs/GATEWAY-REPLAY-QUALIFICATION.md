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
