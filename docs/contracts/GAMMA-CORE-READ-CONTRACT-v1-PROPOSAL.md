# GAMMA ↔ AIOPS Core read contract v1 — proposal for owner approval

**Status:** PROPOSAL ONLY / NOT IMPLEMENTED / NOT APPROVED BY AIOPS OWNERS.  
**Consumer:** GAMMA. **Authority:** canonical AIOPS Core, Evidence and Twin services.  
**Security posture:** all canonical reads remain hard-disabled. This document does not authorize route activation, credentials, data access, deployment or LIVE operations.

## 1. Purpose and non-goals

Define a stable, versioned, read-only boundary so GAMMA can consume canonical operational records without becoming a second incident/run/evidence system of record.

In scope: authenticated, tenant-scoped snapshots and bounded list/detail reads for Incidents, Runs, Evidence and Twin. GLPI remains a separately authorized read adapter and is not implicitly covered by Core authorization.

Out of scope: create/update/delete, incident synchronization, run launch/replay, Policy/HITL decisions, Temporal commands, GLPI writes, arbitrary queries, raw SQL, raw PromQL, arbitrary upstream URLs, and autonomous remediation.

## 2. Trust model

1. The gateway authenticates the human/service actor against an owner-approved IdP.
2. The gateway resolves active tenant membership and requested resource/action against a server-owned ACL. Browser-supplied actor, tenant, role, email, forwarded-user or entity headers are ignored/stripped.
3. The gateway signs a short-lived, request-bound principal assertion. GAMMA verifies issuer, audience, signature, expiry, method/path and service identity.
4. **The source service independently authorizes the same actor + tenant + resource.** GAMMA's HMAC assertion and `tenant_access` claim do not replace Core ACL. A tenant echo in JSON is a consistency check only.
5. Authorization must happen before source/cache reads, pagination, counts, aggregates, graph traversal, evidence resolution or serialization. Denials fail closed and disclose no foreign existence/data.

The current GAMMA assertion verifier uses a shared HMAC secret and has no distributed one-time-use JTI store wired into HTTP authentication. Until replay reservation, gateway bypass prevention, key lifecycle and source-side ACL are qualified, the assertion is not production authorization.

## 3. Versioning and endpoint discovery

Proposed media/schema identifier: `aiops2.read.v1`. Every response includes `schema_version` and a resource `family`.

**No upstream URL or route is approved by this proposal.** AIOPS owners must publish a route manifest for each family containing method, exact path, audience, required scope/action, request schema, response schema, pagination semantics, maximum page size, timeout, freshness policy and error mapping. GAMMA must pin fixed HTTPS origins and owner-approved static paths; never accept a path, host, tenant or cursor authority from the browser.

Candidate resource families (names are logical, not asserted route paths):
- `incidents`
- `runs`
- `evidence`
- `twin`

GLPI must publish a separate actor-to-GLPI-user and entity-permission contract before any GLPI snapshot is considered qualified.

## 4. Common response envelope

The envelope is adapted from the AIOPS read-envelope v0.2 draft and remains subject to owner approval. Required fields:

```json
{
  "schema_version": "aiops2.read.v1",
  "family": "incidents",
  "state": "READY",
  "reason_code": null,
  "data": {},
  "provenance": {
    "source_kind": "canonical_core",
    "source_ref": "opaque-source-reference",
    "observed_at": "2026-11-13T12:00:00Z",
    "collected_at": "2026-11-13T12:00:01Z",
    "snapshot_watermark": "opaque-watermark"
  },
  "freshness": {
    "max_age_seconds": 300,
    "age_seconds": 1,
    "stale": false
  },
  "request": {
    "generation": "opaque-generation",
    "correlation_id": "opaque-correlation-id"
  },
  "page": {
    "next_cursor": null
  }
}
```

Rules:
- `READY`: non-null data, non-empty source_ref and watermark, valid observed/collected timestamps, explicit freshness; stale data is never READY.
- `UNKNOWN`, `ERROR`, `BLOCKED`: `data: null`; absence is never converted to an empty success, zero, healthy or resolved state.
- `BLOCKED` is reserved for an authenticated, authorized request denied by a non-auth policy. Authentication/authorization denials use HTTP 401/403, not a successful envelope.
- Timestamps are timezone-aware RFC3339 UTC. The consumer validates age against server time and per-family policy; schema validation alone cannot prove freshness or provenance.
- Unknown fields are rejected for v1 unless an explicitly versioned extension is approved.

## 5. Request and pagination rules

- All list requests are bounded (proposed default 50, hard maximum 100) and use opaque server-issued cursors.
- Cursors are bound server-side to actor, tenant, resource family, filter set, sort order and snapshot watermark. Tampered, expired or cross-tenant cursors fail with 400/403; never fall back to page one.
- No unbounded history, arbitrary filter expression, client-provided SQL, graph query language or source URL.
- Detail reads require object-level ACL, not just tenant-level membership.
- Counts, facets, aggregates, search results, graph nodes/edges, impact paths, evidence links, citations and exports are separately tenant-scoped; they must not leak through metadata or error differences.

## 6. Required authorization test matrix

Run against disposable PostgreSQL 16 and real HTTP handlers, with two independently authenticated principals and two tenants. Source-level tests are necessary but insufficient.

| Case | Expected result | Must be proven |
|---|---|---|
| Actor A → tenant A | permitted rows only | positive list/detail |
| Actor B → tenant B | permitted rows only | positive list/detail |
| Actor A → tenant B | 403 or tenant-safe 404 | zero foreign rows/counts |
| Forged actor/tenant/role headers | ignored | verified principal wins |
| Revoked membership | 403 | revocation effective before read |
| Foreign object ID | tenant-safe 404/403 | no existence leak |
| Foreign cursor/filter | 400/403 | no page-one fallback |
| Aggregate/count/facet | scoped | no cross-tenant side channel |
| Twin graph/impact traversal | scoped at every hop | no foreign nodes/edges |
| Evidence/citation link | scoped at source and target | no orphaned foreign reference |
| Auth/ACL backend unavailable | 401/403/503 fail closed | zero source/cache reads |
| Timeout/cancel/stale generation | UNKNOWN/error; no partial READY | upstream cancellation and stale-response discard |

Tests must also prove authorization-before-read with spies, no secret/body leakage, safe error normalization, concurrency, revocation, cache isolation and audit records.

## 7. GAMMA consumer requirements

- Continue to keep `enable_canonical_reads=False`, `enable_opensearch=False` and `enable_glpi_reads=False` until independent gates are signed off.
- Keep `fetch_canonical()` unconditional 503 for allowlisted resources. No feature flag may bypass this hold.
- When later approved, use distinct least-privilege service credentials per source, TLS verification, no redirects, no ambient proxies, strict byte/time limits, duplicate-key-safe JSON parsing and infrastructure-enforced egress allowlists.
- Cache keys include issuer, subject, tenant, resource, authorization version, filters and snapshot watermark. No shared cross-tenant cache. Cache invalidation/revocation behavior must be tested.
- Validate the full envelope and resource schema before projection. Preserve UNKNOWN/STALE/BLOCKED; never infer source health from host health.
- GAMMA remains a read-only consumer. No upstream mutation methods or write credentials.

## 8. Owner deliverables required before implementation

AIOPS Core / Gateway owners must provide:
1. Approved IdP/gateway issuer, audience, subject and actor-type contract; signature/JWKS or introspection, key rotation and revocation semantics.
2. Membership and resource ACL model, including action/scope, grantor, lifecycle, audit and revocation latency.
3. Signed assertion schema and secure gateway-to-service network boundary; distributed replay protection and mTLS/service identity.
4. Exact versioned route manifest and OpenAPI/JSON Schemas for Incidents, Runs, Evidence and Twin.
5. Source-side two-tenant HTTP/PostgreSQL evidence for list/detail/count/graph/history/evidence/error paths.
6. Per-family freshness/provenance policy and operational SLO/timeout limits.

GAMMA then prepares a separate implementation PR, pinned to the approved upstream contract version. No branch cherry-pick or draft PR is treated as an authorization provider.

## 9. Acceptance and release gates

- [ ] AIOPS owners approve this contract and publish route/schema manifest.
- [ ] Real IdP/gateway principal and actor→tenant/resource ACL qualified.
- [ ] JTI replay reservation, key rotation, bypass prevention and revocation qualified.
- [ ] Source-side authorization-before-read and cross-tenant matrix pass for every family.
- [ ] GAMMA consumer tests pass on an exact full checkout and exact commit SHA.
- [ ] Disposable PostgreSQL 16 and browser/HTTP integration tests pass.
- [ ] Independent security review, audit review and rollback plan accepted.

**Until all gates pass: HOLD / NO_GO.** No merge-to-stable, deployment, canonical reads, GLPI reads, production data access or LIVE action is authorized by this proposal.
