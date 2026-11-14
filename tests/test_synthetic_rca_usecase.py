"""UC06 synthetic RCA evaluation: citations are not source verification or authority."""
from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.reused.investigation import (
    EvidenceRef, Hypothesis, InvestigationPreview, evaluate_investigation,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


def request(*, tenant=TENANT, verdict="unknown"):
    return InvestigationPreview(
        tenant_id=tenant, incident_id="DEMO-INC-1", started_at=NOW,
        evidence=[
            EvidenceRef(ref_id="demo-trace-1", source="trace", observed_at=NOW),
            EvidenceRef(ref_id="demo-change-1", source="change", observed_at=NOW),
        ],
        hypotheses=[
            Hypothesis(
                hypothesis_id="demo-h1",
                summary="Synthetic deployment timing may explain latency",
                supporting_refs=["demo-trace-1"],
                contradicting_refs=["demo-change-1"],
                verdict=verdict,
            ),
        ],
    )


def test_synthetic_rca_preserves_unknown_and_non_authoritative_provenance():
    result = evaluate_investigation(request(), TENANT)
    assert result["hypothesis_count"] == 1
    assert result["hypotheses_with_evidence"] == 1
    assert result["unknown_hypotheses"] == 1
    assert result["citation_references_resolved"] is True
    assert result["citations_source_verified"] is False
    assert result["human_adjudicated"] is False
    assert result["authoritative"] is False
    assert result["live_execution_authorized"] is False
    assert result["data_source"] == "caller_supplied_preview"


def test_synthetic_rca_cross_tenant_denied():
    with pytest.raises(PermissionError, match="Cross-tenant"):
        evaluate_investigation(request(tenant=OTHER), TENANT)


def test_synthetic_rca_unknown_reference_rejected():
    payload = request().model_dump()
    payload["hypotheses"][0]["supporting_refs"] = ["missing-trace"]
    with pytest.raises(ValidationError, match="Unresolvable evidence reference"):
        InvestigationPreview.model_validate(payload)


def test_synthetic_rca_cannot_use_same_ref_as_support_and_contradiction():
    payload = request().model_dump()
    payload["hypotheses"][0]["contradicting_refs"] = ["demo-trace-1"]
    with pytest.raises(ValidationError, match="Evidence cannot support and contradict"):
        InvestigationPreview.model_validate(payload)


def test_synthetic_rca_supported_label_still_does_not_grant_authority():
    result = evaluate_investigation(request(verdict="supported"), TENANT)
    assert result["supported_hypotheses"] == 1
    assert result["citations_source_verified"] is False
    assert result["live_execution_authorized"] is False
