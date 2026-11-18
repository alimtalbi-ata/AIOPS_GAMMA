"""Offline review receipt pipeline. Never approves or executes a runbook."""
from copy import deepcopy
from app.reused.shadow_review_auth import verify_synthetic_review
from app.reused.shadow_review_replay import consume_synthetic_review


def receive_review(path, envelope, now, attestation, actor, tenant, keys):
    envelope, attestation = deepcopy(envelope), deepcopy(attestation)
    verify_synthetic_review(envelope, now, attestation, actor, tenant, keys)
    report = envelope["body"]["report"]
    if (report.get("review_state") != "REVIEW_CANDIDATE"
            or report.get("approval_state") != "NOT_GRANTED"
            or report.get("authoritative") is not False
            or report.get("live_execution_authorized") is not False
            or report.get("human_review_required") is not True
            or report.get("execution_state") != "NOT_EXECUTED"):
        raise ValueError("Review dossier not eligible")
    result = consume_synthetic_review(path, envelope, now, attestation["claims"]["digest"], tenant)
    return {**result, "authoritative": False, "human_review_required": True,
            "execution_state": "NOT_EXECUTED"}
