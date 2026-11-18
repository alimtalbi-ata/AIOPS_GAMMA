from dataclasses import replace

import pytest

from test_shadow_inbox_rca import inputs
from app.reused.shadow_runbook import RunbookCandidate
from app.reused.shadow_remediation_preview import preview_remediation


def candidate():
    return RunbookCandidate("rb-1", "1", "payment", "timeout", True, True, "latency")


def test_candidate_never_grants_execution():
    receipt, investigation = inputs()
    report = preview_remediation(receipt, investigation, "payment", (), "timeout", (candidate(),))
    assert report["runbook_state"] == "REVIEW_CANDIDATE"
    assert report["rollback_state"] == "DECLARED_ONLY"
    assert report["approval_state"] == "NOT_GRANTED"
    assert report["live_execution_authorized"] is False


@pytest.mark.parametrize("catalog", [(), (candidate(), candidate()),
    (replace(candidate(), rollback_defined=False),), (replace(candidate(), approved=False),)])
def test_unsafe_or_ambiguous_catalog_abstains(catalog):
    receipt, investigation = inputs()
    report = preview_remediation(receipt, investigation, "payment", (), "timeout", catalog)
    assert report["runbook_state"] == "ABSTAIN"


def test_rca_abstention_blocks_runbook():
    receipt, investigation = inputs()
    evidence = (replace(investigation.evidence[0], source_verified=False), investigation.evidence[1])
    report = preview_remediation(receipt, replace(investigation, evidence=evidence),
                                 "payment", (), "timeout", (candidate(),))
    assert report["runbook_state"] == "ABSTAIN"
    assert "RCA_NOT_SUPPORTED" in report["runbook_preview"]["reasons"]
