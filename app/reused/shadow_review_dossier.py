"""Combine shadow remediation preview and risk screen into a review dossier."""
from app.reused.shadow_remediation_preview import preview_remediation
from app.reused.shadow_remediation_risk import screen_risk


def build_review_dossier(receipt, investigation, service, dependencies, symptom, catalog, risk):
    preview = preview_remediation(receipt, investigation, service, dependencies, symptom, catalog)
    assessment = screen_risk(risk)
    reasons = tuple(preview["runbook_preview"]["reasons"]) + tuple(assessment["reasons"])
    eligible = preview["runbook_state"] == "REVIEW_CANDIDATE" and assessment["state"] == "REVIEW_CANDIDATE"
    return {
        **preview,
        "risk_state": assessment["state"],
        "risk_assessment": assessment,
        "review_state": "REVIEW_CANDIDATE" if eligible else "BLOCKED",
        "review_reasons": reasons,
        "human_review_required": True,
        "approval_state": "NOT_GRANTED",
        "execution_state": "NOT_EXECUTED",
        "authoritative": False,
        "live_execution_authorized": False,
    }
