from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.reused.shadow_inbox_rca import SyntheticInboxReceipt, evaluate_inbox_evidence
from app.reused.shadow_investigation import Evidence, Hypothesis, InvestigationInput


def inputs():
    now = datetime.now(timezone.utc)
    receipt = SyntheticInboxReceipt("tenant-a", "INC-1", "event-1", ("log-1", "trace-1"))
    evidence = tuple(Evidence(ref, "tenant-a", "INC-1", "h1", "supports", now, True, source)
                     for ref, source in (("log-1", "logs"), ("trace-1", "traces")))
    investigation = InvestigationInput("tenant-a", "INC-1", (Hypothesis("h1", "Synthetic timeout"),), evidence, now)
    return receipt, investigation


def test_matched_receipt_only_yields_review_candidate():
    receipt, investigation = inputs()
    result = evaluate_inbox_evidence(receipt, investigation)
    assert result["investigation"]["state"] == "REVIEW_CANDIDATE"
    assert result["authoritative"] is False
    assert result["live_execution_authorized"] is False


@pytest.mark.parametrize("change", [
    {"tenant_id": "tenant-b"}, {"incident_id": "INC-2"},
    {"evidence_refs": ("log-1",)}, {"evidence_refs": ("log-1", "log-1")},
])
def test_receipt_mismatch_rejected(change):
    receipt, investigation = inputs()
    with pytest.raises(ValueError):
        evaluate_inbox_evidence(replace(receipt, **change), investigation)


def test_foreign_evidence_abstains():
    receipt, investigation = inputs()
    evidence = (replace(investigation.evidence[0], tenant_id="tenant-b"), investigation.evidence[1])
    result = evaluate_inbox_evidence(receipt, replace(investigation, evidence=evidence))
    assert result["investigation"]["state"] == "ABSTAIN"
    assert result["live_execution_authorized"] is False
