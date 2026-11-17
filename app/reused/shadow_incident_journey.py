"""Offline AIOps incident decision report: compose pure shadow contracts.

Inputs are synthetic and caller-supplied. This orchestration does not read
tenants, operate tools, execute runbooks or certify a real recovery.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.reused.shadow_autonomy import assess_shadow_autonomy
from app.reused.shadow_investigation import InvestigationInput, investigate_shadow
from app.reused.shadow_runbook import RunbookCandidate, plan_shadow_runbook
from app.reused.synthetic_recovery import SLIObservation, assess_synthetic_recovery


@dataclass(frozen=True)
class IncidentShadowInput:
    tenant_id: str
    incident_id: str
    service: str
    symptom: str
    evidence_verified: bool
    topology_verified: bool
    rca_verdict: str
    supporting_refs: int
    contradicting_refs: int
    catalog: tuple[RunbookCandidate, ...]
    policy_approved: bool = False
    hitl_approved: bool = False
    simulated_action_performed: bool = False
    before: SLIObservation | None = None
    after: SLIObservation | None = None
    sli_max_value: float = 250.0
    investigation: InvestigationInput | None = None


def evaluate_incident_shadow(req: IncidentShadowInput) -> dict:
    """Return traceable, explicitly non-authoritative stage decisions."""
    if type(req) is not IncidentShadowInput:
        raise ValueError("Invalid shadow incident")
    if (type(req.tenant_id) is not str or not req.tenant_id.strip()
            or type(req.incident_id) is not str or not req.incident_id.strip()):
        raise ValueError("Missing tenant or incident identity")
    investigation_report = None
    if req.investigation is not None:
        investigation_report = investigate_shadow(req.investigation)
        if (investigation_report["tenant_id"] != req.tenant_id
                or investigation_report["incident_id"] != req.incident_id):
            raise ValueError("Investigation identity mismatch")
    # Synthetic investigation cannot certify upstream evidence or override
    # caller RCA flags; with an investigation attached, always fail closed.
    evidence_qualified = req.evidence_verified and investigation_report is None
    rca_qualified = req.rca_verdict == "supported" and investigation_report is None
    runbook = plan_shadow_runbook(
        service=req.service, symptom=req.symptom, catalog=req.catalog,
        rca_supported=rca_qualified
        and req.supporting_refs > 0 and req.contradicting_refs == 0
        and evidence_qualified,
    )
    autonomy = assess_shadow_autonomy(
        evidence_source_verified=evidence_qualified,
        topology_source_verified=req.topology_verified,
        rca_verdict=req.rca_verdict if investigation_report is None else "unknown",
        supporting_evidence_count=req.supporting_refs,
        contradicting_evidence_count=req.contradicting_refs,
        runbook_approved=runbook.state == "REVIEW_CANDIDATE",
        policy_approved=req.policy_approved,
        hitl_approved=req.hitl_approved,
    )
    if type(req.simulated_action_performed) is not bool:
        raise ValueError("Invalid synthetic action flag")
    recovery = assess_synthetic_recovery(
        before=req.before if req.simulated_action_performed else None,
        after=req.after if req.simulated_action_performed else None,
        max_acceptable_value=req.sli_max_value,
    )
    # Even caller-supplied 'approved' booleans do not constitute a real
    # approval or authorization. This report never starts an execution.
    return {
        "tenant_id": req.tenant_id,
        "incident_id": req.incident_id,
        "service": req.service,
        "mode": "synthetic_shadow",
        "stages": {
            **({"investigation": investigation_report} if investigation_report is not None else {}),
            "runbook": asdict(runbook),
            "autonomy": asdict(autonomy),
            "recovery": asdict(recovery),
        },
        "execution_state": "SYNTHETIC_ACTION_ONLY" if req.simulated_action_performed else "NOT_EXECUTED",
        "itsm_mutations_performed": False,
        "authoritative": False,
        "live_execution_authorized": False,
    }
