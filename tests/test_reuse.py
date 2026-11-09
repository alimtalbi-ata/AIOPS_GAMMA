import pytest

from app.reused.contracts import project_run_evidence
from app.reused.impact import STAGES, estimate_impact, transition
from app.reused.tenant_scope import reject_unqualified_tenant_scope


def test_impact_from_existing_aiops_domain():
    assert estimate_impact(0.1, 0, 4).state == "OUTAGE"
    assert estimate_impact(0.0, 3, 4).state == "DEGRADED"
    assert estimate_impact(0.1, 4, 4).state == "NONE"
    assert estimate_impact(0.5, 0, 0).state == "UNKNOWN"
    assert estimate_impact(0.5, 0, 0).live_remediation_authorized is False


def test_invalid_topology_rejected():
    with pytest.raises(ValueError):
        estimate_impact(0.1, 5, 4)


def test_state_machine():
    assert transition("CREATED", "RUNNING") == "RUNNING"
    with pytest.raises(ValueError):
        transition("RESOLVED", "RUNNING")
    assert "HITL" in STAGES


def test_unqualified_tenant_claims_rejected():
    with pytest.raises(ValueError):
        reject_unqualified_tenant_scope({"metadata": [{"Tenant-ID": None}]})


def test_synthetic_only_run_projection():
    row = project_run_evidence({"run_id": "run-1", "incident_id": "inc-1", "mode": "REPLAY"})
    assert row["live_remediation_authorized"] is False
    with pytest.raises(ValueError):
        project_run_evidence({"run_id": "run-1", "incident_id": "inc-1", "mode": "LIVE"})
