# Trusted actor→tenant principal — implementation status and release gate

Status: **PARTIAL IMPLEMENTATION / NO_GO**. GAMMA now verifies a signed gateway assertion in addition to its internal service credential. This is not production authorization approval: the Core/Gateway owner must implement and approve the signing contract, tenant-membership decision, network boundary, key management and replay controls.

## Implemented in GAMMA

`app/security.py` now requires both:
- `X-Internal-API-Key`: authenticates the calling workload only; it does not authorize a tenant.
- `X-Gateway-Principal`: a compact `base64url(payload).base64url(HMAC-SHA256)` assertion signed with a separate secret.

The assertion is bound to the exact HTTP method and path and must contain:
- `iss` / `aud`: configured issuer and audience;
- `sub` and `actor_type` (`user` or `service`);
- canonical non-nil `tenant_id` and `tenant_access: true`;
- integer `iat` / `exp` with a lifetime no longer than configured maximum (default 60 seconds);
- unique-looking `jti` assertion identifier;
- `method` and `path` matching the actual request.

The caller-supplied `X-Tenant-ID`, `X-Actor-ID`, role and user headers are not used to construct the principal. Missing/invalid signing configuration fails closed. The assertion secret must be at least 32 UTF-8 bytes. Tokens are capped at 8 KiB and malformed base64/signatures fail closed. Docker Compose now forwards the gateway assertion settings to the API container; an unset secret keeps protected routes unavailable (503). The internal service credential remains separately required.

Configuration:
- `GATEWAY_ASSERTION_SECRET` (unset by default; configure only after secret provisioning approval)
- `GATEWAY_ASSERTION_ISSUER` (default `gamma-gateway`)
- `GATEWAY_ASSERTION_AUDIENCE` (default `aiops-gamma`)
- `GATEWAY_ASSERTION_MAX_TTL_SECONDS` (default `60`)

## Required gateway behavior — NOT implemented/verified here

1. Authenticate actor using the organization's approved identity provider and validate issuer, audience, signature, expiry and subject.
2. Query the server-owned ACL and authorize the actor for the selected tenant and requested resource. Only then may the gateway set `tenant_access: true` and sign the assertion.
3. Strip inbound identity, role and tenant headers. Never trust a browser-supplied assertion.
4. Sign with a separate high-entropy secret (or migrate to asymmetric signing with `kid` and key rotation). The secret must not be the internal service API key.
5. Restrict network ingress so callers cannot bypass the gateway. Use mTLS/service identity where available.
6. Add shared replay protection for `jti` (e.g. short-lived distributed one-time-use store). GAMMA currently enforces short TTL and method/path binding but does **not** keep a distributed replay cache; the same valid assertion could be replayed on the same method/path until expiry.
7. Define revocation semantics and ensure membership revocation is reflected before the next authorized request.

## Replay and key-management limitations

GAMMA currently validates `jti` syntax but does **not** persist or consume assertion IDs. A valid assertion can therefore be replayed on the same method/path until expiry. Short TTL and request binding reduce exposure but do not prevent replay. Before production, add a shared atomic one-time-use store (e.g. Redis `SET NX EX` or a PostgreSQL unique constraint with expiry cleanup), test concurrent duplicate submissions across API replicas, and fail closed if that store is unavailable. HMAC shared-secret rotation also requires a coordinated versioned key identifier/overlap policy; this is not implemented yet.

## Mandatory validation still outstanding

- [ ] Gateway owner approves assertion schema and implements actor→tenant/resource ACL.
- [ ] Gateway and GAMMA share provisioned/rotatable signing secret; key rotation and compromise response tested.
- [ ] Replay cache, gateway bypass restrictions and mTLS/network policy verified.
- [ ] Real HTTP tests through the complete application verify tenant A cannot access tenant B data or resource IDs.
- [ ] Positive tests prove an authorized actor can read only the permitted tenant.
- [ ] Revocation and authorization-backend outage tests fail closed.
- [ ] Versioned Core/Evidence/Twin contracts and source-side ACL independently verified.
- [ ] Full repository tests and deployment qualification reviewed.

Until every gate is closed, keep `enable_canonical_reads=False`, `enable_opensearch=False`, `enable_glpi_reads=False`, draft PRs and **NO_GO** for merge, deployment and LIVE.


## Proposed replay reservation implementation — not enabled

The new isolated helper `app/gateway_replay.py:reserve_assertion_once` uses a PostgreSQL atomic `INSERT ... ON CONFLICT DO NOTHING RETURNING` on a SHA-256 digest of `issuer + NUL + jti`. The proposed `gateway_assertion_replay` table must have `assertion_digest` as its unique primary key and `expires_at` as a timezone-aware timestamp. It intentionally has **no automatic table creation or runtime integration**.

Before wiring into `internal_principal`, an owner must review and deploy an Alembic migration, then ensure the reservation transaction is committed **before** a protected handler can run; rolling back the reservation with a later failed business transaction would reopen replay. Expired reservations must be cleaned only after the assertion expiry plus permitted clock skew, and the cleanup must never remove unexpired reservations. Concurrent requests across API replicas and a database outage must be tested. A duplicate reservation must return 401/409 without resource access, and any database error must fail closed. No process-local fallback is permitted.

The helper's fake-session tests cover duplicate detection, issuer separation and database-error propagation, but **do not prove Postgres concurrency, migration safety or end-to-end protection**. The API currently does not call this helper; replay remains a release blocker.


### Committed replay-reservation helper (still not wired)

The helper `consume_assertion_before_access` now performs `reserve_assertion_once`, then **commits the reservation before returning success**. Duplicate reservations return false after rollback. Commit failure triggers rollback and propagates the error (no access grant). This must use a dedicated session, not a later handler transaction. Fake-session tests cover successful commit, duplicate denial and commit failure; these are not real PostgreSQL transaction/concurrency proofs.

**Do not enable or wire this helper yet.** First deploy a reviewed migration for the unique replay table, verify behavior with actual PostgreSQL across API replicas and ensure the gateway ACL and network boundary are approved. All sensitive reads and LIVE remain HOLD.


### Replay migration staged (2026-11-11)

`migrations/versions/0002_gateway_replay.py` now follows `0001_initial` and creates `gateway_assertion_replay` with a 64-character SHA-256 digest primary key and indexed timezone-aware `expires_at`. `app/models.py` registers the same table in SQLAlchemy metadata.

An isolated SQLite/Alembic DDL smoke test verified upgrade, duplicate primary-key rejection and downgrade (3/3). **This is not a PostgreSQL transaction/concurrency test** and does not prove that the migration was deployed. The replay helper remains unwired to HTTP authentication. Do not apply this migration to production without DBA review, PostgreSQL qualification and a tested rollback plan.


### Opt-in real PostgreSQL concurrency qualification (not yet executed)

The test module `tests/test_gateway_replay_postgres.py` now provides two integration checks using **independent async PostgreSQL sessions**: two concurrent reservations of the same issuer/JTI must yield exactly one success, and a later session must reject a committed replay. The tests require an **explicit disposable** `GAMMA_REPLAY_TEST_DATABASE_URL` using the `postgresql+asyncpg://` driver and a database where reviewed migration `0002_gateway_replay` has already been applied. With no URL, the tests skip rather than touching an existing database; they only delete their own randomly generated reservation rows. Do not run them against production or staging.

Suggested isolated qualification command after provisioning a disposable PostgreSQL database and applying Alembic migrations:

```bash
GAMMA_REPLAY_TEST_DATABASE_URL='postgresql+asyncpg://test_user:...@localhost:5432/gamma_replay_test' \
  python -m pytest -q tests/test_gateway_replay_postgres.py
```

**No PostgreSQL server was available in the current ChatGPT lab**; these tests are committed but have not passed against PostgreSQL. HTTP replay rejection and the real gateway actor→tenant ACL remain unverified. Keep the replay helper unwired and the release on HOLD.


### Disposable PostgreSQL test guard (2026-11-11)

The opt-in PostgreSQL test fixture now refuses connection URLs that do not use `postgresql+asyncpg` and a database name ending in `_replay_test`. It checks `SELECT current_database()` after connection and before writing. Four isolated URL-guard checks passed in the ChatGPT lab (three unsafe URLs rejected; one disposable test URL accepted). These are **guard-only unit checks**, not the two PostgreSQL concurrency tests. An explicitly named test database is necessary but not sufficient: operators must still ensure the target is genuinely disposable and isolated.

The lab has neither PostgreSQL server binaries nor `asyncpg`; therefore **the real PostgreSQL concurrency tests remain unexecuted**. The replay component remains unwired and HOLD / NO_GO remains in effect.

### Replay test target restriction (2026-11-11)

The opt-in PostgreSQL concurrency harness now additionally rejects **remote hosts**, even when the database name ends in `_replay_test`. Only `localhost`, `127.0.0.1` or `::1` are accepted. A local port-forward to a production database is still unsafe; the operator must provision an actually disposable isolated instance and verify its identity. Five targeted SQLAlchemy URL-parser checks passed in the ChatGPT container (2 local accepted, 3 unsafe driver/database/remote host rejected). The real PostgreSQL tests are still unexecuted; the lab has no PostgreSQL server or asyncpg. This change does not enable the replay gate or LIVE reads.

### Trusted assertion expiry propagation (2026-11-11)

The verified `Principal` now retains the integer signed `exp` as `expires_at` (commit `be5f71f`). The assertion verification test checks that a valid signed expiry is preserved (`1060` in the deterministic fixture). This prepares an eventual call to `consume_assertion_before_access` without taking expiry from untrusted request headers. **No replay reservation is invoked in `internal_principal` yet**, and the current API must not be represented as replay-protected. The updated full application tests have not been executed in this change; PostgreSQL qualification and Gateway ACL remain outstanding.

### HTTP gateway-assertion boundary regression coverage (2026-11-11)

`tests/test_tenant_http_auth_boundary.py` now contains an HTTP test that sends a correctly signed short-lived gateway assertion plus the separate service key to `POST /api/v1/observability/metrics/query`, expecting its intentional `501` (the route performs no tenant read). Three HTTP negative cases require `401`: wrong signed path, `tenant_access: false`, and a modified signature. These are regression tests **committed but not yet executed against the full repository**; do not infer passing HTTP coverage. This is signed-assertion validation, **not** replay-consumption or actor→tenant ACL verification. The replay helper is still unwired and HOLD / NO_GO remains.

### HTTP regression reliability and dual-credential check (2026-11-11)

The HTTP tampered-signature test now modifies the **first** Base64URL signature character, not the last (which may only change unused padding bits). An isolated Python HMAC/Base64URL check confirmed that the first-character mutation changes the decoded signature bytes. Added an HTTP regression requiring `401` when a valid signed gateway assertion is supplied with an invalid internal service key. These HTTP tests are committed but **not executed in the full FastAPI test suite**. The standalone signature-byte check is not an HTTP test. PostgreSQL replay concurrency, Gateway ACL and network ingress remain unverified; HOLD / NO_GO.

### HTTP tenant-header spoofing probe (2026-11-11)

The HTTP auth boundary tests now include a small in-test FastAPI probe route using the **real** `internal_principal` dependency. It signs a principal for tenant A, sends unsigned `X-Tenant-ID` for tenant B and forged actor/role headers, then asserts the returned principal still contains tenant A and the signed subject. This checks the actual derived identity instead of merely inferring correctness from the metrics endpoint's 501 response. It does not read tenant resources or activate replay protection. The test has been committed but **not executed in this turn**; real Gateway ACL, PostgreSQL replay concurrency and network restrictions remain unverified. HOLD / NO_GO.

### HTTP fail-closed configuration and expiry cases (2026-11-11)

Added HTTP regression cases for missing gateway verification secret (expected `503` with service key and otherwise valid signed assertion) and expired but correctly HMAC-signed assertion (expected `401`). A **separate isolated FastAPI harness**, not the repository's `app.main` or actual security module, executed 3/3 assertions for valid, expired, and missing-secret behavior. The new repository tests have **not** been executed and must not be represented as passing. Real PostgreSQL replay consumption and actor→tenant/resource ACL are still unverified; HOLD / NO_GO.

### Signed assertion time-boundary regression cases (2026-11-11)

`tests/test_gateway_assertion.py` now explicitly tests `iat` more than five seconds in the future, boolean `iat`/`exp` values, expiration at issuance, a lifetime of 61 seconds against the 60-second policy, and rejection exactly at `now == exp`. These six tests are committed but **not executed in the full repository environment**. They do not validate Gateway ACL, shared replay state, PostgreSQL or LIVE readiness. HOLD / NO_GO.

### Fail-closed gateway assertion TTL configuration (2026-11-11)

The verifier now rejects a configured `gateway_assertion_max_ttl_seconds` outside **1..60** with HTTP `503` before verifying the token. This prevents an operator misconfiguration from silently accepting long-lived signed assertions. A lower positive configured maximum remains supported and is enforced against signed `exp - iat`. Five new unit test cases cover 0, -1, 61, 3600 and a stricter 30-second limit. **These new repository tests have been committed but not executed in this turn**. This does not activate shared replay consumption or replace Gateway actor→tenant/resource ACL. HOLD / NO_GO.

### Strict TTL configuration type check (2026-11-11)

The verifier now requires `type(gateway_assertion_max_ttl_seconds) is int` as well as a value between 1 and 60 inclusive. This closes Python's `bool`-as-`int` corner case and rejects fractional policy overrides in tests. The repository parametrized regression includes `True`, `False` and `30.5`. A **separate local pytest harness reproducing only this TTL guard** passed 10/10 cases (7 invalid, 3 valid); **the repository's actual verifier and full test suite were not executed**. No PostgreSQL replay, Gateway ACL or ingress qualification; HOLD / NO_GO.

### Signed replay identifier input hardening (2026-11-11)

The verifier now requires the signed `jti` to be an 8–128-character ASCII string containing only printable non-whitespace bytes (`!` through `~`). This prevents blank, control-character, and non-ASCII replay IDs from entering future shared replay reservations. Unit regression coverage includes missing/short/long IDs, whitespace-only, embedded newline and Unicode. **Nine isolated local Python checks** of the guard expression passed, but the full repository tests and real PostgreSQL replay tests have **not** been run. The replay helper remains unwired to HTTP, and Gateway actor→tenant ACL is still unverified. HOLD / NO_GO.

### GitHub Actions verification — 2026-11-11

At commit `c86cd485b3cac1d2462a36dd3f2458831710aa07`, GitHub reported two completed failed workflow runs: `Python checks` (`43082228771`) and `Deployment contract (static + runtime smoke)` (`43082228809`). The former contained failed jobs `frontend` and `test`; the latter contained failed jobs `postgres-nonroot-experiment`, `ui-image`, `compose`, `helm`, `single-directory-runtime`, and `api-postgres-runtime`. Job details returned no step summaries (`steps: null`), so this is **not evidence that tests ran and failed** or that any test passed. Do not use these runs as security qualification. Continue with independent disposable lab execution and preserve HOLD / NO_GO.

### Disposable PostgreSQL schema revision preflight (2026-11-11)

The opt-in replay concurrency fixture now checks `SELECT version_num FROM alembic_version` and requires the exact reviewed revision `0002_gateway_replay` **before test writes**, in addition to checking the connected database name and replay table presence. Missing `alembic_version`, a wrong revision, or a database error fail the fixture closed. This change has **not** been exercised against a real PostgreSQL instance; it does not demonstrate that the migration applies or that concurrent reservations work. A loopback connection can still be a tunnel to a sensitive database, so human confirmation of a disposable target remains mandatory. HOLD / NO_GO.

### Explicit disposable PostgreSQL write opt-in and bounded test row expiry (2026-11-11)

The opt-in PostgreSQL replay fixture now requires `GAMMA_REPLAY_TEST_ALLOW_WRITE=I_UNDERSTAND_DISPOSABLE_DB` **as well as** a loopback PostgreSQL URL naming `*_replay_test`, a matching connected database name, replay table, and exact Alembic revision `0002_gateway_replay`. The two integration tests now use `expires_at = int(time.time()) + 300` rather than year 2100, limiting the retention horizon of orphaned test rows **only if a separate expiry cleanup process exists**; expiry does not automatically delete rows. This acknowledgement is a safeguard, **not proof that a loopback/forwarded database is disposable**. No real PostgreSQL tests were executed; Gateway ACL, replay HTTP wiring, CI and ingress remain blocking. HOLD / NO_GO.

### Replay helper input type checks — local execution (2026-11-11)

`reserve_assertion_once` now rejects non-string issuer/JTI and non-integer or nonpositive expiry values before issuing SQL. Eight new parametrized fake-session cases cover `None`, numeric IDs, boolean, fractional, string and zero expiry. **Executed locally** with the updated helper and contract test file: `python -m pytest -q tests/test_gateway_replay_contract.py` → **13 passed in 0.28s**. This validates the isolated helper with fake sessions, not PostgreSQL concurrency, the full repository test suite, or HTTP replay enforcement. HOLD / NO_GO.

### Replay digest delimiter and JTI canonicalization (2026-11-11)

The replay helper now rejects NUL (`\\x00`) in the issuer to avoid ambiguous `issuer + NUL + jti` digest inputs, and rejects JTI values unless they are 8–128 printable, non-whitespace ASCII characters, matching the signed assertion verifier. Six regression cases cover NUL issuer, short/blank/newline/Unicode/oversized JTI. **Executed:** a local isolated pytest harness using a manually materialized copy of the updated replay helper, with six negative cases and one positive case: **7 passed in 0.23s**. This is not a synchronized checkout or full repository test execution, and it does not prove PostgreSQL concurrency or HTTP enforcement. HOLD / NO_GO.

### Replay consume rollback error paths — local test execution (2026-11-11)

Added two contract tests asserting `consume_assertion_before_access` rolls back and does not commit when a replay key is invalid or a simulated SQL INSERT fails. **Executed** against the manually materialized replay helper and test file in the internal lab: `python -m pytest -q tests/test_gateway_replay_contract.py` → **21 passed in 0.24s**. This is fake-session unit evidence, not a PostgreSQL integration run or byte-for-byte synchronized repository checkout. Gateway ACL, HTTP replay wiring, CI and live Postgres qualification remain outstanding. HOLD / NO_GO.


### Replay-store retention and availability gate (2026-11-11)

**Unresolved operational prerequisite — not an authorization to enable replay enforcement.** The current migration creates an indexed `expires_at` column, but the reservation helper only inserts and checks uniqueness of `assertion_digest`; **it does not delete expired records**. An expired assertion cannot become valid again through cleanup: the signature verifier must continue enforcing `exp`, `iat`, maximum TTL, method/path and tenant claims independently. However, without an approved retention job, the replay table grows indefinitely, creating storage and availability risk.

Before enabling replay enforcement, the owner must approve and test a bounded, observable PostgreSQL cleanup policy (for example, batched deletion of rows older than a conservative grace period), with a documented maximum storage budget, cleanup failure alerting, and concurrency tests proving no duplicate can be accepted during cleanup. Never delete unexpired reservations, never treat database errors as permission to proceed, and never rely on a process-local replay cache. The replay reservation must be committed in a dedicated transaction **before** any protected work. The exact cleanup interval/grace period remains **TBD** pending review; no cleanup is deployed or scheduled.

**Evidence boundary:** this is a source-level gap identified by inspection of `app/gateway_replay.py` and migration schema, not a PostgreSQL load or retention test. Gateway actor→tenant/resource ACL, HTTP integration, migration approval and CI remain blocking. **HOLD / NO_GO**.
