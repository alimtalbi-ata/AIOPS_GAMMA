from dataclasses import replace

from test_shadow_inbox_rca import inputs
from app.reused.shadow_rca_trace import build_trace_report


def test_trace_links_and_review_boundary():
    receipt, investigation = inputs()
    result = build_trace_report(receipt, investigation, "payment", ())
    assert {link["evidence_ref"] for link in result["trace_links"]} == {"log-1", "trace-1"}
    assert all(link["event_id"] == "event-1" and link["hypothesis_id"] == "h1"
               for link in result["trace_links"])
    assert result["human_review_required"] is True
    assert result["approval_state"] == "NOT_GRANTED"
    assert result["live_execution_authorized"] is False


def test_rejected_evidence_visible_but_not_linked_as_support():
    receipt, investigation = inputs()
    evidence = (replace(investigation.evidence[0], source_verified=False), investigation.evidence[1])
    result = build_trace_report(receipt, replace(investigation, evidence=evidence), "payment", ())
    assert result["investigation"]["state"] == "ABSTAIN"
    assert ("log-1", "UNVERIFIED_SOURCE") in result["rejected_evidence"]
    assert all(link["evidence_ref"] != "log-1" for link in result["trace_links"])
