# Canonical read adapter — qualification contract

**Security status (2026-11-12): HARD HOLD / NO_GO.** The endpoint `GET /api/v1/canonical/{resource}/snapshot` now refuses all allowlisted resources with HTTP 503 `Canonical actor/tenant/resource ACL not qualified`, **even when** `ENABLE_CANONICAL_READS=true`. It performs no upstream network request. Unknown resources still return 404. This prevents a misconfigured feature flag or an echoed tenant ID from being mistaken for independently verified actor→tenant→resource authorization.

The original prototype and its planned transport contract are historical design context only, **not active code**. Source of truth: `app/reused/upstream.py` and `tests/test_upstream.py`. The `validate_origin` helper remains available for future configuration qualification; it does not authorize any fetch.

Before a future separately reviewed activation: choose an authoritative IdP/gateway, verify the actor and tenant membership server-side, enforce per-resource Core/Evidence/Twin ACL upstream, test cross-tenant and revoked identities with real HTTP/PostgreSQL, and validate egress/transport controls. Related aiops design review: https://github.com/alimtalbi-ata/aiops/pull/668. No provider has been selected by assumption.

---

Status: **prototype, disabled by default**. This is a first bounded network adapter, not proof of upstream API compatibility.

- Endpoint: `GET /api/v1/canonical/{resource}/snapshot`, where resource is strictly `core`, `evidence`, or `twin`. Internal API key + tenant UUID required.
- Fixed HTTPS origin settings: `CORE_READ_URL`, `EVIDENCE_READ_URL`, `TWIN_READ_URL` (origins only); `CANONICAL_READ_TOKEN`; `ENABLE_CANONICAL_READS=false` by default.
- Only GET, static paths, no redirects, no environment proxies, TLS verification, 3-second timeout, max 256 KiB, JSON object only.
- A successful response **must include** `tenant_id` matching the gateway tenant UUID; missing/mismatched tenant is rejected. This is an additional consistency check, **not** independent proof of upstream ACL.
- Generic 502/503 errors do not reveal upstream secrets or response bodies.
- The static resource paths are **provisional**; check against real `aiops` Core/Evidence/Twin routes and auth before enabling. No GLPI mutation or direct database access.
- This adapter deliberately does not provide DNS pinning or prevent DNS rebinding by itself. Enforce egress policy and internal service identity at the network layer.
- `X-Tenant-Id` is still trusted only behind a separately authenticated gateway. **Do not expose this API directly to browser users or production networks.**
- There is no automatic retry, cache, pagination or service-to-service OIDC/mTLS in this slice.

## Before activation

1. Validate upstream path/auth schema, tenant ACL and response tenant attestation.
2. Use distinct least-privilege upstream credentials, rotate and store in secret manager.
3. Add egress DNS/IP allowlist, OIDC/mTLS and per-resource authorization.
4. Test negative tenant cases and cross-service identity; audit all reads.
5. Qualify timeout, circuit breaker, telemetry, bounded pagination and schema validation.

Until then, leave the flag disabled. The response is an opaque tenant-attested JSON snapshot, **not** a verified incident or RCA object.
