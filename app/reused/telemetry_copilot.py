"""Read-only guided Copilot preview, without free-text model or tools."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from app.reused.telemetry_rca_critic import critique_telemetry
from app.reused.unified_telemetry import TelemetryObservation

Intent = Literal["summary", "hypotheses", "blockers", "next_checks"]
_INTENTS = ("summary", "hypotheses", "blockers", "next_checks")


def copilot_preview(items: list[TelemetryObservation], *, tenant_id: UUID,
                    incident_id: str, incident_grants: frozenset[str],
                    grants: frozenset[tuple[str, str]],
                    bindings: dict[tuple[str, str], str], now: datetime,
                    intent: Intent = "summary") -> dict:
    """Server-owned tenant, incident grants, resource grants and bindings only."""
    if not isinstance(incident_grants, frozenset) or not isinstance(incident_id, str) or incident_id not in incident_grants:
        raise PermissionError("Incident access denied")
    if not isinstance(intent, str) or intent not in _INTENTS:
        raise ValueError("Unsupported Copilot intent")
    result = critique_telemetry(items, tenant_id=tenant_id,
                               incident_id=incident_id, grants=grants,
                               bindings=bindings, now=now)
    analyst = result["analyst"]
    report = analyst["investigation"]
    refs = {ref["ref_id"]: ref for ref in report["evidence"]}
    cited = set()
    if intent == "summary":
        answer = {"hypothesis_count": len(report["hypotheses"]),
                  "decision": result["decision"], "excluded": analyst["excluded"],
                  "coverage_incomplete": "INCOMPLETE_CANDIDATE_COVERAGE" in result["findings"]}
    elif intent == "hypotheses":
        answer = {"hypotheses": report["hypotheses"], "context": analyst["questions"]}
        cited = {ref for question in analyst["questions"] for ref in question["context_refs"]}
    elif intent == "blockers":
        answer = {"findings": result["findings"], "reviews": result["reviews"]}
        cited = {ref for review in result["reviews"] for ref in review["context_refs"]}
    else:
        checks = {check for question in analyst["questions"] for check in question["required_checks"]}
        checks.update(("Verify incident-to-resource association", "Obtain authorized source observations"))
        answer = {"checks": sorted(checks)}
    return {"schema_version": "gamma.copilot.preview.v1",
            "tenant_id": str(tenant_id), "incident_id": incident_id,
            "as_of": now.astimezone(timezone.utc).isoformat(),
            "intent": intent, "answer": answer,
            "context_references": [refs[ref] for ref in sorted(cited)],
            "decision": result["decision"], "model_invoked": False,
            "source_authenticated": False, "incident_association_verified": False,
            "root_cause_confirmed": False, "authoritative": False,
            "live_remediation_authorized": False}
