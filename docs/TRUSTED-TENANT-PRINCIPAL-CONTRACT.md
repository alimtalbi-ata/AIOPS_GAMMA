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
