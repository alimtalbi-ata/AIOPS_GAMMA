# OpenSearch log read contract — P1/P2 qualification

**Status: HOLD / NO_GO.** This document is a deployment qualification checklist, not an authorization to enable the adapter.

## Expected document shape

GAMMA sends a tenant-scoped, service-scoped, time-bounded, optionally severity-scoped query against the configured `opensearch_logs_index`. Its response validator requires the following fields on every returned `_source`:

```json
{
  "tenant": {"id": "11111111-1111-4111-8111-111111111111"},
  "resource": {"attributes": {"service.name": "checkout"}},
  "@timestamp": "2026-11-10T11:57:00Z",
  "severityText": "ERROR"
}
```

The `severityText` field is mandatory only when a severity filter was requested. A tenant identifier and service name must always be present and exact. The timestamp must include a timezone and fall inside the requested window.

**This is a GAMMA adapter contract, not proof that the live OTel/OpenSearch ingest pipeline produces this shape.** OTel collector exporters and index mappings can flatten or rename attributes; inspect a redacted sample from the target index before enabling the feature flag. In particular, confirm that `tenant.id` is a trusted ingest-side attribute, not an untrusted log-producer claim.

## Required pre-enable checks

1. Confirm the actual index template, `tenant.id`, `resource.attributes.service.name`, `@timestamp` and `severityText` mappings, and exact-match keyword behavior. Do not silently weaken the validator to match an unverified mapping.
2. Configure a dedicated read-only OpenSearch principal with index permissions restricted to the intended log indices. Verify server-side document-level security (DLS) for tenant isolation **or** an equivalent independently enforced tenant-specific index boundary. GAMMA's query filters and response validation are defense in depth, not an authorization boundary.
3. Prove cross-tenant requests are denied at the cluster boundary, including direct API calls with modified DSL, not only through GAMMA.
4. Use verified HTTPS for remote endpoints, credentials outside URLs, and a bounded explicit index prefix. Confirm certificate trust and credential rotation.
5. Exercise a real tenant-specific log read, zero-hit case, wrong-tenant document, wrong-service document, missing timestamp, and severity mismatch in staging. Confirm failures are returned as sanitized errors without disclosing raw upstream data.
6. Confirm trusted gateway actor→tenant membership and **resource-level** authorization before permitting any non-demo tenant log read. The current signed assertion proves gateway-attested tenant membership, not resource entitlement.
7. Record evidence, approver, rollback/disable procedure, and CI results in the PR before any decision to change `enable_opensearch`.

## Scope and limitations

The adapter requests only reviewed metadata through an OpenSearch `_source.includes` filter, enforces a 1 MiB upstream JSON response budget, and projects only reviewed metadata (`@timestamp`, `tenant.id`, `resource.attributes.service.name`, and optional `severityText`) into API responses. Raw log bodies, arbitrary attributes, OpenSearch index IDs and highlights are not returned. This is intentional until an independently reviewed redaction policy and resource-level authorization are available. The size check happens after the backend response is received, so it is not a streaming memory bound. No LIVE remediation, merge, deployment, or adapter activation is authorized by this document.
