"""Offline RCA review. Recompute analyst output from scoped inputs."""
from datetime import datetime
from uuid import UUID

from app.reused.telemetry_rca_analyst import analyze_telemetry
from app.reused.unified_telemetry import TelemetryObservation


def critique_telemetry(items: list[TelemetryObservation], *, tenant_id: UUID,
                       incident_id: str, grants: frozenset[tuple[str, str]],
                       bindings: dict[tuple[str, str], str], now: datetime,
                       window_seconds: int = 120, max_age_seconds: int = 300) -> dict:
    """Review only server-recomputed context; no caller verdict is trusted."""
    analyst = analyze_telemetry(items, tenant_id=tenant_id, incident_id=incident_id,
                                grants=grants, bindings=bindings, now=now,
                                window_seconds=window_seconds,
                                max_age_seconds=max_age_seconds)
    findings = [
        "SOURCE_AUTHENTICITY_UNVERIFIED",
        "INCIDENT_ASSOCIATION_UNVERIFIED",
        "NO_CAUSAL_EVIDENCE",
        "COUNTER_AND_WINDOW_SEMANTICS_UNVERIFIED",
        "NO_HUMAN_ADJUDICATION",
    ]
    if analyst["graph_truncated"] or analyst["omitted_services"]:
        findings.append("INCOMPLETE_CANDIDATE_COVERAGE")
    if analyst["excluded"]["stale"]:
        findings.append("STALE_OBSERVATIONS_EXCLUDED")
    if analyst["excluded"]["unmapped"]:
        findings.append("UNMAPPED_OBSERVATIONS_EXCLUDED")
    if not analyst["questions"]:
        findings.append("NO_CROSS_SOURCE_CANDIDATES")
    reviews = [
        {"hypothesis_id": question["hypothesis_id"],
         "context_refs": question["context_refs"],
         "verdict": "unknown",
         "confidence": None,
         "blockers": ["TEMPORAL_PROXIMITY_ONLY", "NO_VERIFIED_SUPPORT",
                      "NO_VERIFIED_COUNTEREVIDENCE"],
         "contradiction_state": "NOT_ASSESSED",
         "required_checks": question["required_checks"]}
        for question in analyst["questions"]
    ]
    return {"schema_version": "gamma.rca.critic.preview.v1",
            "analyst": analyst, "reviews": reviews, "findings": findings,
            "decision": "INSUFFICIENT_EVIDENCE",
            "root_cause_confirmed": False, "model_invoked": False,
            "human_adjudicated": False, "authoritative": False,
            "live_remediation_authorized": False}
