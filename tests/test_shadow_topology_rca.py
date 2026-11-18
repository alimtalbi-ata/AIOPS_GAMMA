import pytest

from test_shadow_inbox_rca import inputs
from app.reused.shadow_topology_rca import SyntheticDependency, evaluate_topology_rca


def test_topology_context_does_not_authorize_causation():
    receipt, investigation = inputs()
    edges = (SyntheticDependency("tenant-a", "frontend", "payment"),
             SyntheticDependency("tenant-a", "payment", "database"))
    result = evaluate_topology_rca(receipt, investigation, "payment", edges)
    assert result["topology"]["neighbors"] == (("downstream", "database"), ("upstream", "frontend"))
    assert result["topology"]["causation_established"] is False
    assert result["topology"]["source_verified"] is False
    assert result["live_execution_authorized"] is False


def test_foreign_topology_rejected_even_if_unrelated():
    receipt, investigation = inputs()
    with pytest.raises(ValueError, match="Topology tenant mismatch"):
        evaluate_topology_rca(receipt, investigation, "payment",
                              (SyntheticDependency("tenant-b", "other", "db"),))
