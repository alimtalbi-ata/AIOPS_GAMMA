"""Offline RCA-to-runbook preview. No execution or approval interface."""
from dataclasses import asdict
from app.reused.shadow_rca_trace import build_trace_report
from app.reused.shadow_runbook import plan_shadow_runbook


def preview_remediation(receipt, investigation, service, dependencies, symptom, catalog):
    report = build_trace_report(receipt, investigation, service, dependencies)
    plan = plan_shadow_runbook(
        service=service, symptom=symptom, catalog=catalog,
        rca_supported=report["investigation"]["state"] == "REVIEW_CANDIDATE",
    )
    return {
        **report,
        "runbook_state": plan.state,
        "runbook_preview": asdict(plan),
        "risk_state": "NOT_ASSESSED",
        "rollback_state": "DECLARED_ONLY" if plan.state == "REVIEW_CANDIDATE" else "NOT_SELECTED",
        "human_review_required": True,
        "approval_state": "NOT_GRANTED",
        "execution_state": "NOT_EXECUTED",
        "live_execution_authorized": False,
    }
