# Evidence-linked investigation preview (experimental)

## Current capability

`POST /api/v1/incidents/investigation/preview` is a strictly typed, authenticated **read-only evaluation** of caller-supplied incident evidence and RCA hypotheses. It does not run an agent, query telemetry, verify the underlying source content, store findings, adjudicate causal accuracy, create ITSM tickets, or execute remediation. The canonical Core remains incident owner.

Requires trusted internal gateway headers `X-Internal-Api-Key` and `X-Tenant-Id`. Request `tenant_id` must match the authenticated principal (403 otherwise). No direct browser exposure.

Example (synthetic):

```json
{
  "tenant_id": "00000000-0000-0000-0000-000000000001",
  "incident_id": "INC-123",
  "started_at": "2026-11-09T10:00:00Z",
  "evidence": [
    {"ref_id": "trace:123", "source": "trace", "observed_at": "2026-11-09T10:01:00Z"}
  ],
  "hypotheses": [
    {"hypothesis_id": "h1", "summary": "Possible upstream timeout", "supporting_refs": ["trace:123"], "contradicting_refs": [], "verdict": "supported"}
  ]
}
```

Evidence types: `metric`, `log`, `trace`, `change`, `topology`, `code`, `runbook`. All timestamps must have timezone offsets. Limits: 100 evidence refs, 20 hypotheses, 30 refs per supporting/contradicting list, bounded text fields. Unknown fields are rejected. A hypothesis cannot cite the same ref as supporting and contradicting; all cited IDs must exist in the request. A `supported` verdict requires at least one supporting reference.

Response includes `evidence_count`, `hypothesis_count`, `hypothesis_evidence_coverage_pct`, counts by verdict, and flags `citation_references_resolved=true`, `citations_source_verified=false`, `human_adjudicated=false`, `authoritative=false`, `live_execution_authorized=false`. **Citation resolution means only that a supplied ID exists in the same request; it is not cryptographic verification, a provenance guarantee, or evidence of causality.** No process KPI such as RCA accuracy, MTTR, time-to-RCA or model cost is claimed from this preview.

## Next steps

1. Add immutable source/tenant/incident-bound evidence IDs with read-only upstream attestation, time-window checks and source provenance.
2. Implement bounded investigation stages and tool receipts behind tenant-scoped allowlists; no arbitrary code execution.
3. Establish human-reviewed RCA evaluation fixtures with known UNKNOWN/contradictory cases, then compute trustworthy process KPIs from verified timestamps.
4. Build a React Investigation Workbench using explicit `PREVIEW` / `UNVERIFIED` / `UNKNOWN` states.
5. Introduce reviewable postmortem drafts; keep execution strictly behind independent Policy/HITL gates.

See [PRODUCT-UX-DESIGN](PRODUCT-UX-DESIGN.md) and [LLM-KPI-CONTRACT](LLM-KPI-CONTRACT.md).
