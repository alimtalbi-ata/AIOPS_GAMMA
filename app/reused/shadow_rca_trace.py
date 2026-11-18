"""Offline traceability report over synthetic Inbox and topology contracts."""
from app.reused.shadow_topology_rca import evaluate_topology_rca


def build_trace_report(receipt, investigation, service, dependencies):
    report = evaluate_topology_rca(receipt, investigation, service, dependencies)
    rca = report["investigation"]
    links = tuple(
        {"event_id": receipt.event_id, "hypothesis_id": h["hypothesis_id"],
         "evidence_ref": ref, "stance": stance}
        for h in rca["hypotheses"]
        for stance, refs in (("supports", h["supporting_refs"]),
                             ("contradicts", h["contradicting_refs"]))
        for ref in refs
    )
    return {
        **report,
        "trace_links": links,
        "rejected_evidence": rca["rejected_evidence"],
        "decision_reasons": rca["reasons"],
        "runbook_state": "NOT_EVALUATED",
        "human_review_required": True,
        "approval_state": "NOT_GRANTED",
        "trace_origin": "CALLER_DECLARED_SYNTHETIC",
    }
