# ITIL 4 — ITSM incident synchronization contract

**Status:** pure preview, not a GLPI/ServiceNow/Jira Service Management connector.

## Design
- Enterprise-owned, **versioned 3×3 priority matrix** maps incident impact and urgency to an enterprise-specific priority. Unknown values remain UNKNOWN; no hard-coded global P1–P5 formula.
- ITSM external ticket references are opaque, system-qualified, and authoritative.
- Propose-create refuses an already-linked ITSM ticket; propose-enrichment requires an exact existing ITSM reference.
- Proposals require evidence refs and tenant equality.
- Stable SHA-256 idempotency key identifies the *logical proposal*. It is **not** a distributed exactly-once guarantee; canonical Core and ITSM adapters must implement persistence, transactional outbox and downstream reconciliation.
- No HTTP requests, credentials, ITSM mutation, change approval, CMDB updates, or remediation execution.

## Internal API
`POST /api/v1/itil4/incidents/sync-preview`

Request:
```json
{
  "incident": {
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "incident_id": "INC-123",
    "impact": "high",
    "urgency": "medium",
    "evidence_refs": ["trace-1"]
  },
  "matrix": {
    "policy_id": "enterprise-matrix",
    "version": "2026-01",
    "rules": [
      {"impact": "high", "urgency": "high", "priority": "P1"},
      {"impact": "high", "urgency": "medium", "priority": "P2"},
      {"impact": "high", "urgency": "low", "priority": "P3"},
      {"impact": "medium", "urgency": "high", "priority": "P2"},
      {"impact": "medium", "urgency": "medium", "priority": "P3"},
      {"impact": "medium", "urgency": "low", "priority": "P4"},
      {"impact": "low", "urgency": "high", "priority": "P3"},
      {"impact": "low", "urgency": "medium", "priority": "P4"},
      {"impact": "low", "urgency": "low", "priority": "P5"}
    ]
  },
  "operation": "propose_create"
}
```

**Security limitation:** The matrix is caller-supplied *for preview only*. A real connector must resolve the immutable policy/version from an enterprise-controlled policy store, never accept arbitrary priorities or workflow transitions from the browser/LLM. Internal principal tenant still depends on a trusted gateway. The endpoint is advisory only.

## Next integration gates
1. Independently authenticated tenant and scoped enterprise policy lookup.
2. Vendor-specific, version-pinned GLPI/ServiceNow/JSM contract tests.
3. Canonical Core incident ownership, durable idempotency and replay-safe ticket reconciliation.
4. Service management RBAC, audit receipts, CMDB validation and SLA policy.
5. Stage-based verification with mock servers and real staging tenant isolation before any ITSM writes.
