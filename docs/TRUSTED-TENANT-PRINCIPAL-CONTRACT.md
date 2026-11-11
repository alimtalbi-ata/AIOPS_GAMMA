# Trusted actor→tenant principal — integration gate (draft, NOT implemented)

Status: **BLOCKED / NO_GO**. This document specifies a contract to be agreed with the Core/Gateway owner; it does not grant authority, enable any reads, or claim an implementation.

## Current boundary

`app/security.py:internal_principal` verifies `X-Internal-API-Key` against one shared service secret and parses caller-supplied `X-Tenant-ID` into a canonical non-nil UUID. `Principal` contains only `tenant_id`. A caller holding the shared key can select another tenant UUID. A gateway trust assumption in a comment is not enforced actor authentication or tenant ACL. Do not expose these endpoints to untrusted callers or treat tenant-filtered SQL as proof of authorization.

`app/reused/upstream.py` sends the selected tenant UUID in `X-Tenant-Id` and checks that the upstream JSON echoes `tenant_id`; an echo is **not** an authorization attestation. The provisional upstream paths (`/api/v1/incidents`, `/api/v1/evidence`, `/api/v1/topology`) do not match inspected Core/Evidence/Twin routes. Do not remap them to global routes without a new reviewed contract.

## Required Core/Gateway-owned contract (design only)

1. **Authenticated actor:** gateway authenticates a human or explicitly scoped workload identity, verifies issuer, audience, signature, expiry, not-before and subject; a service API key alone cannot impersonate a human. A stable actor identifier, actor type and request correlation ID must be available to the authorization decision.
2. **Trusted boundary:** only an authenticated, network-restricted gateway may assert verified principal data; it must strip any inbound user-supplied identity/tenant headers before adding its own. Direct service bypass must be denied. Specify signed assertion or server-side introspection and key rotation, replay protection, TTL and failure behavior; never trust unsigned browser headers.
3. **Server-owned tenant membership:** authorization service derives permitted tenants and resource-level privileges from a server-owned ACL for the verified actor. The requested tenant is an untrusted *selection*, not proof of membership. Deny absent/revoked membership and unauthorized resource IDs **before** fetching or serializing data.
4. **Bounded read response:** upstream endpoints must be versioned and document their actual paths, request/response schemas, provenance, tenant scoping and freshness. Responses must be validated against the authorization decision; matching an echoed tenant string is insufficient. No mutation or ITSM write in read adapters.
5. **Failure mode:** absent/invalid/expired principal, unreachable authorization service, stale membership or missing tenant-scope attestation must fail closed; no fallback to `X-Tenant-ID`, a service key, global endpoints, or demo data represented as LIVE.

## Mandatory executable HTTP acceptance matrix (not yet passed)

| Case | Expected result |
|---|---|
| No credential or invalid service credential | Deny; no upstream request |
| Valid shared service key only + tenant A | Deny as a human principal; no upstream request |
| Same service key with tenant A then tenant B, without verified membership | Deny both or deny unauthorized tenant; no cross-tenant records |
| Forged principal, actor, role or tenant headers | Ignore/deny; no privilege escalation |
| Expired/bad-signature/wrong-audience assertion | Deny; no upstream request |
| Verified actor with tenant A membership requests tenant B | 403 or deliberately non-disclosing 404; no tenant B data |
| Verified actor with tenant A membership requests tenant B resource ID | Deny without revealing resource contents or existence |
| Membership revoked after a prior successful request | Deny on next authorization decision under agreed revocation policy |
| Authorization backend unavailable or ambiguous | Deny; never fall back to service-key/header-only access |
| Verified actor with permitted tenant and resource | Scoped read only; prove no mixed-tenant rows, bounded response and provenance |
| Upstream malformed, stale, oversized, redirect or timeout | Safe bounded error; no raw secret or upstream URL exposure |

Tests must execute through real HTTP dependencies (including gateway bypass attempts), not just call a pure Python helper. Verify gateway and upstream independently; preserve logs and exact commit SHA.

## Release gates

- [ ] Core/Gateway owner approves issuer/audience/subject, actor types, tenant membership, revocation and gateway assertion verification.
- [ ] Versioned Core/Evidence/Twin endpoints and source-side tenant/resource ACL verified, with real response schemas.
- [ ] Negative and positive HTTP tests above run and pass in a controlled environment; evidence attached.
- [ ] Network ingress/egress restrictions and secrets rotation qualified; no direct service bypass.
- [ ] GitHub Actions or independently accepted equivalent complete repository test evidence reviewed; GitHub Actions currently fails before steps.
- [ ] Security reviewer explicitly authorizes a separate staging enablement decision.

Until then retain `enable_canonical_reads=False`, `enable_opensearch=False`, `enable_glpi_reads=False`, draft PR #1 and **NO_GO** for merge, deployment and LIVE.
