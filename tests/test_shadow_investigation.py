"""Safety and decision tests for offline multi-hypothesis RCA."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.reused.shadow_investigation import (
    Evidence, Hypothesis, InvestigationInput, investigate_shadow,
)

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
H = (Hypothesis("database", "Database saturation"), Hypothesis("network", "Network issue"))


def evidence(ref, hypothesis="database", stance="supports", **overrides):
    return replace(Evidence(ref, "tenant-a", "inc-1", hypothesis, stance, NOW, True, ref), **overrides)


def request(*items, **overrides):
    return replace(InvestigationInput("tenant-a", "inc-1", H, tuple(items), NOW), **overrides)


def test_unique_supported_hypothesis_is_review_only():
    result = investigate_shadow(request(evidence("metric"), evidence("trace")))
    assert result["state"] == "REVIEW_CANDIDATE"
    assert result["selected_hypothesis_id"] == "database"
    assert result["authoritative"] is False
    assert result["live_execution_authorized"] is False
    assert result["tools_invoked"] is False
    assert result["itsm_mutations_performed"] is False


def test_conflicting_evidence_forces_abstention():
    result = investigate_shadow(request(evidence("metric"), evidence("trace"),
                                          evidence("counter", stance="contradicts")))
    assert result["state"] == "ABSTAIN"
    assert result["selected_hypothesis_id"] is None
    assert "CONTRADICTORY_EVIDENCE" in result["hypotheses"][0]["reasons"]


def test_two_plausible_causes_are_ambiguous():
    result = investigate_shadow(request(evidence("a"), evidence("b"),
                                          evidence("c", "network"), evidence("d", "network")))
    assert result["state"] == "ABSTAIN"
    assert "AMBIGUOUS_OR_UNSUPPORTED_RCA" in result["reasons"]


@pytest.mark.parametrize("change,reason", [
    ({"tenant_id": "tenant-b"}, "IDENTITY_MISMATCH"),
    ({"incident_id": "other"}, "IDENTITY_MISMATCH"),
    ({"source_verified": False}, "UNVERIFIED_SOURCE"),
    ({"hypothesis_id": "invented"}, "UNKNOWN_HYPOTHESIS"),
    ({"observed_at": NOW - timedelta(hours=1)}, "OUT_OF_WINDOW"),
    ({"observed_at": NOW + timedelta(seconds=1)}, "OUT_OF_WINDOW"),
])
def test_rejected_evidence_cannot_be_used_to_prove_rca(change, reason):
    result = investigate_shadow(request(evidence("good"), evidence("bad", **change)))
    assert result["state"] == "ABSTAIN"
    assert ("bad", reason) in result["rejected_evidence"]


def test_missing_evidence_abstains():
    assert investigate_shadow(request())["state"] == "ABSTAIN"


@pytest.mark.parametrize("items,overrides", [
    ((evidence("same"), evidence("same")), {}),
    ((), {"hypotheses": (H[0], H[0])}),
    ((), {"max_age_seconds": 0}),
    ((), {"min_independent_sources": 1}),
    ((), {"tenant_id": ""}),
    ((), {"as_of": NOW.replace(tzinfo=None)}),
    ((evidence("bad", source_verified="yes"),), {}),
    ((evidence("bad", observed_at=NOW.replace(tzinfo=None)),), {}),
])
def test_invalid_inputs_fail_closed(items, overrides):
    with pytest.raises(ValueError):
        investigate_shadow(request(*items, **overrides))


def test_duplicate_source_identity_does_not_count_twice():
    result = investigate_shadow(request(
        evidence("metric", source_id="otel"),
        evidence("trace", source_id="otel"),
    ))
    assert result["state"] == "ABSTAIN"
    assert "INSUFFICIENT_SUPPORT" in result["hypotheses"][0]["reasons"]
    assert result["hypotheses"][0]["supporting_source_ids"] == ("otel",)


def test_missing_source_identity_abstains():
    result = investigate_shadow(request(
        evidence("metric", source_id=""),
        evidence("trace", source_id="trace"),
    ))
    assert result["state"] == "ABSTAIN"
    assert ("metric", "MISSING_SOURCE_ID") in result["rejected_evidence"]


def test_source_ids_are_synthetic_not_execution_authority():
    result = investigate_shadow(request(
        evidence("metric", source_id="metrics"),
        evidence("trace", source_id="traces"),
    ))
    assert result["state"] == "REVIEW_CANDIDATE"
    assert result["hypotheses"][0]["supporting_source_ids"] == ("metrics", "traces")
    assert result["authoritative"] is False
    assert result["live_execution_authorized"] is False


def test_whitespace_source_alias_does_not_fake_independence():
    result = investigate_shadow(request(
        evidence("metric", source_id="otel"),
        evidence("trace", source_id=" otel "),
    ))
    assert result["state"] == "ABSTAIN"
    assert result["hypotheses"][0]["supporting_source_ids"] == ("otel",)
