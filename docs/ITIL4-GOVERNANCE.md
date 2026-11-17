# AIOPS_GAMMA — ITIL 4 governance and ITSM interoperability

**Target:** work in ITIL 4-aligned enterprise environments (GLPI, ServiceNow, Jira Service Management and other ITSM platforms), without assuming that a particular vendor's workflow or priority matrix is universal. This document is a design target, **not** proof of official certification or production conformity.

## Four practices and authority boundaries

| ITIL 4 practice | AI SRE role | Data contracts | Authority and control |
|---|---|---|---|
| Incident management | detect, triage, correlate, enrich and propose priority based on impact/urgency | `IncidentAssessment`, evidence references, affected CIs, source events | Enterprise ITSM owns ticket lifecycle, priority matrix, assignment, SLA and closure; AI cannot declare a resolved ticket without verification |
| Problem management | correlate recurrence, build RCA hypotheses, identify suspected known errors and workarounds | `ProblemAssessment`, supporting/contradictory evidence, known error ref | Problem manager/ITSM validates root cause, problem record and known error database (KEDB) |
| Change enablement | propose a change or remediation RFC, describe impacted CIs, risk, implementation, test and rollback plan | `ChangeProposal`, versioned runbook, verification plan and ITSM change ref | Change authority / approved standard-change model owns authorization; **normal/emergency procedures depend on enterprise policy** |
| Service configuration management | match OTel-discovered services to CMDB CI records, flag drift and unknown ownership | `ObservedCI`, provenance, observation timestamp, verified CI refs | CMDB remains authoritative for CI identifiers and relationships; discovery alone never updates CMDB without approved reconciliation |

**Important ITIL 4 nuance:** The practice is commonly called *change enablement* in ITIL 4, rather than treating every change as a CAB-approved RFC. A pre-authorized **standard change** may be handled by an approved change model; **normal changes** require the appropriate configured change authority and **emergency changes** follow a dedicated authorized route. Gamma must not hard-code “every RFC needs manual approval” as a universal rule, nor automatically approve any change based on the string `standard`.

## Additional ITIL 4 practices to support

- **Monitoring and event management:** OTel/Cortex/OpenSearch signals, deduplication, event lifecycle and alert quality.
- **Service level management:** service SLIs, SLOs, error budgets, SLA context and customer impact.
- **Knowledge management:** evidence-backed runbooks, KEDB entries, postmortems and review.
- **Service request management:** only for approved request models, never confuse request fulfilment with incident remediation.
- **Information security management:** separation of duties, least privilege, retention and secret redaction.
- **Deployment management / release management:** correlate deploys/changes with incident timeline; retain authoritative deployment and version IDs.
- **Continual improvement:** post-incident reviews, root-cause benchmarks, reduction in toil/MTTD/MTTR and measurable automation success/failure.

## Integration flow

1. Observe a signal: source fingerprint and timestamp recorded, preserve source authenticity/freshness and tenant scope.
2. Correlate within the canonical Core incident lifecycle (Gamma preview is not the authoritative writer).
3. Resolve service-to-CI relationships only via independently verified CMDB mappings; record unknown or stale mapping as **UNKNOWN**.
4. Enrich ITSM incident using an idempotent adapter, authoritative ITSM priority matrix and assignment policy; attach evidence links, not raw credentials.
5. Detect a recurrent pattern; propose a *problem* and suspected known error; human validation required to mark a root cause confirmed.
6. Prepare a remediation/change proposal with explicit affected CIs, runbook/version, implementation/rollback/verification plans, risk grade and confidence.
7. Delegate decision to independent Policy/HITL and configured ITSM change authority; a standard-change model must be pre-authorized for the **exact procedure and scope**, not merely named “standard”.
8. Only the existing `aiops` Core → Temporal/Worker may execute an action after an independently validated enterprise change authorization and policy receipt; enforce fencing and idempotency.
9. Verify SLIs and changes, update ITSM incident/problem/change links, preserve audit and postmortem, track continuous improvement.

## Minimum objects and relationships

```
tenant / business service
  ├── CI (CMDB record, authoritative owner)
  ├── event (source fingerprint, observed_at, trust)
  ├── incident (ITSM ticket, impact, urgency, assignment and SLAs)
  │     ├── problem (RCA hypothesis, known error, KEDB; optional)
  │     ├── change (RFC / standard-change model; optional)
  │     ├── evidence (logs, traces, metrics, change history)
  │     └── approved runbook/version (specific CI + approved scope)
  └── verification (SLIs, customer impact, audit, continuous improvement)
```

## Implemented this slice: preview-only

- `app/reused/itil.py`: strict schemas for incident, problem, change and observed CIs, tenant equality and cross-reference checks; verified CI gating for **draft generation**.
- `POST /api/v1/itil4/workflow/preview`: internal-authenticated, read-only classification and dependency projection with explicit *not approved*, *ITSM mutation not performed* and *LIVE forbidden* statuses.
- Unit tests for tenant mismatch, incident linking, unknown priority, unverified CI and denial of implied standard-change approval.

## System-of-record contract (for later adapters)

For each enterprise ITSM (GLPI, ServiceNow, JSM), map:
- Idempotency key: `tenant + source + canonical incident ID + operation`; replay returns canonical ticket reference.
- Reference ownership: external ticket ID, problem ID, change ID and CI IDs remain ITSM-provided (never fabricate).
- Direction: Gamma/AI may propose updates; ITSM independently decides priority, assignment, workflow transition and change approval.
- Audit: actor, tenant, evidence IDs, reason, policy version, change model, timestamps, decision and downstream receipt.
- Race handling: avoid duplicate tickets, stale workflow transitions, out-of-order event closure and cross-tenant relationship leakage.
- Privacy: redact credentials/PII in investigation context; use least privilege and explicit retention.

## Acceptance / rollout

1. Agree on process ownership and configured priority matrix with the target enterprise.
2. Validate mappings against each live ITSM vendor/version and tenant-scoped RBAC.
3. Test happy-path and rejection cases for Incident → Problem → Change → CI; no direct source-supplied CI authority.
4. Test emergency/normal/standard change classes against approved enterprise change models.
5. Validate audits, failure reconciliation and ticket idempotency in staging.
6. Demonstrate independent authorization, rollback and outcome checks before LIVE changes.

Current state: **architecture and advisory contracts only**, not a certified or functioning ITIL 4 integration.
