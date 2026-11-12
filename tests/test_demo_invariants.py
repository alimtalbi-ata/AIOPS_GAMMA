"""Synthetic demo invariants: deterministic, read-only and never authoritative.

These checks use only pure in-repository functions. They need no VM, Docker,
PostgreSQL, IdP, external observability backend or production credentials.
"""
from copy import deepcopy

from app.demo import synthetic_correlation_demo, synthetic_investigation_demo


def test_correlation_demo_is_deterministic_and_non_authoritative():
    first = synthetic_correlation_demo()
    second = synthetic_correlation_demo()
    assert first == second
    assert first["mode"] == "synthetic_demo"
    assert first["authoritative"] is False
    result = first["correlation"]
    assert result["source_events"] == 2
    assert len(result["groups"]) == 1
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False
    assert result["groups"][0]["root_cause_state"] == "UNKNOWN"
    assert result["groups"][0]["itsm_ticket_state"] == "NOT_CREATED"


def test_investigation_demo_is_deterministic_and_never_verifies_provenance():
    first = synthetic_investigation_demo()
    second = synthetic_investigation_demo()
    assert first == second
    assert first["mode"] == "synthetic_demo"
    assert first["authoritative"] is False
    assert first["evidence_source_verified"] is False
    result = first["investigation"]
    assert result["evidence_join_complete"] is True
    assert result["evidence_join_consistent"] is True
    assert result["unmatched_evidence"] == 0
    assert result["evidence_duplicates"] == 0
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False
    assert len(result["groups"]) == 1
    group = result["groups"][0]
    assert group["evidence_state"] == "UNVERIFIED"
    assert group["evidence_covered_events"] == 2
    assert group["evidence_missing_events"] == 0
    assert group["root_cause_state"] == "UNKNOWN"
    assert group["itsm_ticket_state"] == "NOT_CREATED"
    assert len(group["evidence"]) == 2
    assert {e["external_id"] for e in group["evidence"]} == {
        "demo-payment-timeout-1", "demo-payment-timeout-2"
    }
    assert all(e["integrity"] == "UNVERIFIED" for e in group["evidence"])
    assert all(e["freshness"] == "FRESH" for e in group["evidence"])


def test_mutating_one_result_does_not_change_next_demo():
    before = synthetic_investigation_demo()
    altered = deepcopy(before)
    altered["investigation"]["groups"][0]["evidence"].clear()
    assert len(synthetic_investigation_demo()["investigation"]["groups"][0]["evidence"]) == 2
