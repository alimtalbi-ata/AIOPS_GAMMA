"""Deterministic RCA questions over unverified telemetry; no model invocation."""
from datetime import datetime
from uuid import UUID

from app.reused.telemetry_evidence_graph import build_evidence_graph
from app.reused.unified_telemetry import TelemetryObservation
from app.reused.investigation import EvidenceRef, Hypothesis, InvestigationPreview, evaluate_investigation


def analyze_telemetry(items: list[TelemetryObservation], *, tenant_id: UUID,
                      incident_id: str, grants: frozenset[tuple[str, str]],
                      bindings: dict[tuple[str, str], str], now: datetime,
                      window_seconds: int = 120, max_age_seconds: int = 300) -> dict:
    graph = build_evidence_graph(items, tenant_id=tenant_id, grants=grants,
                                 bindings=bindings, now=now,
                                 window_seconds=window_seconds,
                                 max_age_seconds=max_age_seconds)
    nodes = {node["id"]: node["observation"] for node in graph["nodes"]}
    hypotheses = []
    questions = []
    refs = {}
    # One exploratory hypothesis per explicitly mapped service, bounded by
    # the existing investigation contract. Select one pair, not a confidence rank.
    services = {}
    for edge in graph["edges"]:
        services.setdefault(edge["service_id"], edge)
    for index, (service, edge) in enumerate(sorted(services.items())[:20]):
        pair = [edge["from"], edge["to"]]
        hypothesis_id = f"temporal-{index + 1}"
        for ref in pair:
            refs[ref] = EvidenceRef(ref_id=ref, source="metric",
                                    observed_at=nodes[ref]["observed_at"])
        hypotheses.append(Hypothesis(
            hypothesis_id=hypothesis_id,
            summary=f"Possible shared operational change affecting {service}; not established.",
            verdict="unknown",
            supporting_refs=[], contradicting_refs=[],
        ))
        questions.append({
            "hypothesis_id": hypothesis_id, "context_refs": pair,
            "service_id": service, "confidence": None,
            "alternatives": ["Independent coincident measurements",
                             "Collection delay or counter reset",
                             "Shared upstream dependency or unrelated workload change"],
            "required_checks": ["Authenticate source and service binding",
                                "Check counter deltas, reset and aligned measurement windows",
                                "Compare baseline, logs, traces and deployment history"],
        })
    request = InvestigationPreview(tenant_id=tenant_id, incident_id=incident_id,
                                   started_at=now, evidence=list(refs.values()),
                                   hypotheses=hypotheses)
    evaluation = evaluate_investigation(request, tenant_id)
    return {"schema_version": "gamma.rca.analyst.preview.v1",
            "investigation": request.model_dump(mode="json"),
            "evaluation": evaluation, "questions": questions,
            "omitted_services": max(0, len(services)-20),
            "graph_truncated": graph["truncated"],
            "excluded": graph["excluded"],
            "model_invoked": False, "root_cause_confirmed": False,
            "live_remediation_authorized": False}
