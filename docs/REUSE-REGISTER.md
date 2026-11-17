# Reuse register — repositories under alimtalbi-ata

Review performed on repository default branches. This is a source-level review, **not** an integration qualification or a license clearance for redistribution.

| Source | Disposition | Rationale |
|---|---|---|
| `aiops/app/shared/domain.py` | **Adapted** as `app/reused/impact.py` | Pure stage/state transition and impact-estimation helpers. Score is not a causal diagnosis. |
| `aiops/app/shared/tenant_scope.py` | **Adapted** as `app/reused/tenant_scope.py` | Fail-closed rejection of unqualified upstream tenant claims; not an ACL implementation. |
| `aiops/app/portal/noc_correlation.py` | **Contract ideas only** | Canonical Run matching rejects LIVE without independently qualified tenant ACL. Avoid copying its portal-specific networking. |
| `aiops/app/copilot/main.py` | **Contract ideas only** | Evidence-first/UNKNOWN semantics; actual Core/Twin/Evidence API adapters need authenticated contracts. |
| `aiops/app/portal/platform_registry.py` | **Contract ideas only** | Preserve UNKNOWN for absent/stale observations; do not copy hard-coded infrastructure addresses. |
| `aiops` Core/Temporal/Policy/Evidence | **Integrate later, do not replace** | Existing platform owns lifecycle, HITL, evidence and remediation. Requires integration tests and source owner review. |
| `observability-stack` | **Upstream integration, not vendored** | Pin official OTel/Data Prepper/APM stack, validate index mappings and security. |
| `holmesgpt` | **Evaluate as optional RCA adapter** | Large third-party codebase; inspect licensing, configuration, safety and evaluation suite before reuse. |
| `aiops-debian-audit` | **Do not copy** | Runtime inventory and potentially sensitive infrastructure details, not reusable application code. |
| `aiops-recovery-data` | **Do not copy** | Database and service backups; must never be imported into Gamma. |
| `aiops-debian-rebuild-private` | **No code reuse** | Only README found. |

## Security invariants

- No LIVE remediation or production authorization can be inferred from a signed NOC source, synthetic Run, LLM confidence or matching IDs.
- The `X-Tenant-Id` header is only trusted behind a separately authenticated, authorized gateway.
- Source-derived impact estimates must carry `UNVERIFIED_TOPOLOGY_ESTIMATE` and `live_remediation_authorized=false`.
- All reuse is additive to the existing Gamma feature branch, with no copying of credentials, environment files, backups, or host-specific endpoints.

## Next engineering work

1. Obtain the authenticated Core, Evidence and Twin API contracts and compose network topology.
2. Build read-only adapters with fixed service origins, timeouts, response bounds and tenant ACL.
3. Validate CMDB mapping and RCA shadow mode with synthetic incidents before LIVE use.
4. Add integration tests for PostgreSQL, OpenSearch, outbox relay and tenant boundaries.
