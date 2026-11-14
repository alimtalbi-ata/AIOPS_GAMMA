import pytest

from app.reused.topology_preview import preview_service_dependencies as preview


def test_transitive_dependencies_are_sorted_and_nonauthoritative():
    result = preview(
        "service", ["service", "app", "db", "cache"],
        [("service", "app"), ("app", "db"), ("service", "cache")],
    )
    assert result["dependency_ids"] == ["app", "cache", "db"]
    assert result["dependency_count"] == 3
    assert result["topology_state"] == "CALLER_SUPPLIED_PREVIEW"
    assert result["cycle_detected"] is False
    assert result["canonical_cmdb_verified"] is False
    assert result["authoritative"] is False
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False


def test_cycles_are_detected_without_recursion():
    result = preview("service", ["service", "app"], [
        ("service", "app"), ("app", "service"),
    ])
    assert result["cycle_detected"] is True
    assert result["topology_state"] == "UNKNOWN"
    assert result["dependency_ids"] == ["app"]


def test_missing_endpoint_is_unknown_not_silently_accepted():
    result = preview("service", ["service", "app"], [
        ("service", "app"), ("app", "missing"),
    ])
    assert result["unresolved_edge_detected"] is True
    assert result["topology_state"] == "UNKNOWN"


def test_diamond_dependency_is_not_a_cycle():
    result = preview("service", ["service", "a", "b", "db"], [
        ("service", "a"), ("service", "b"), ("a", "db"), ("b", "db"),
    ])
    assert result["cycle_detected"] is False
    assert result["dependency_ids"] == ["a", "b", "db"]


@pytest.mark.parametrize("nodes,edges", [
    (["service", "service"], []),
    (["service", ""], []),
    (["service"], [("service",)]),
    (["service"], [("service", 3)]),
    (["service"] * 201, []),
    (["service"], [("service", "service")] * 1001),
])
def test_malformed_or_unbounded_topology_is_rejected(nodes, edges):
    with pytest.raises(ValueError):
        preview("service", nodes, edges)


def test_unrelated_nodes_are_not_in_dependency_set():
    result = preview("service", ["service", "app", "unrelated"], [
        ("service", "app"),
    ])
    assert result["dependency_ids"] == ["app"]


def test_shared_dependency_and_cross_edge_are_not_false_cycles():
    # "b" is both a direct child and reachable through "a".
    result = preview("service", ["service", "a", "b", "db"], [
        ("service", "a"), ("service", "b"),
        ("a", "b"), ("b", "db"),
    ])
    assert result["dependency_ids"] == ["a", "b", "db"]
    assert result["cycle_detected"] is False
    assert result["topology_state"] == "CALLER_SUPPLIED_PREVIEW"


def test_back_edge_to_active_ancestor_is_a_real_cycle():
    result = preview("service", ["service", "a", "b"], [
        ("service", "a"), ("a", "b"), ("b", "a"),
    ])
    assert result["cycle_detected"] is True
    assert result["topology_state"] == "UNKNOWN"
    assert result["live_remediation_authorized"] is False
