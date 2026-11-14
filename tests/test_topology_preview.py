import pytest

from app.reused.topology_preview import (
    preview_service_dependencies as preview,
    preview_upstream_dependents,
)


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


@pytest.mark.parametrize("bad_id", [
    " service", "service ", "service\nother", "service\x7fother",
    "x" * 256, "",
])
def test_invalid_service_identifier_rejected(bad_id):
    with pytest.raises(ValueError):
        preview(bad_id, [bad_id], [])


@pytest.mark.parametrize("bad_id", [
    " db", "db ", "db\nother", "db\x00other", "x" * 256,
])
def test_invalid_node_identifier_rejected(bad_id):
    with pytest.raises(ValueError):
        preview("service", ["service", bad_id], [])


@pytest.mark.parametrize("bad_id", [
    " missing", "missing ", "missing\nother", "missing\x00other", "x" * 256,
])
def test_invalid_edge_endpoint_rejected_instead_of_unknown(bad_id):
    with pytest.raises(ValueError):
        preview("service", ["service"], [("service", bad_id)])


def test_canonical_missing_endpoint_remains_unknown():
    result = preview("service", ["service"], [("service", "missing")])
    assert result["unresolved_edge_detected"] is True
    assert result["topology_state"] == "UNKNOWN"
    assert result["authoritative"] is False


def test_dependency_hops_are_shortest_path_not_dfs_discovery_order():
    result = preview("service", ["service", "a", "b", "db"], [
        ("service", "a"), ("a", "b"), ("b", "db"),
        ("service", "db"),
    ])
    assert result["dependency_hops"] == {"a": 1, "b": 2, "db": 1}
    assert result["dependency_count"] == 3
    assert result["authoritative"] is False


def test_dependency_hops_are_permutation_and_duplicate_invariant():
    nodes = ["service", "a", "b", "db"]
    edges = [
        ("service", "a"), ("service", "b"),
        ("a", "db"), ("b", "db"),
    ]
    first = preview("service", nodes, edges)
    second = preview("service", list(reversed(nodes)), list(reversed(edges)) + [edges[0]])
    assert first == second
    assert first["dependency_hops"] == {"a": 1, "b": 1, "db": 2}


def test_dependency_hops_exclude_unrelated_nodes_and_service_cycle():
    result = preview("service", ["service", "a", "unrelated"], [
        ("service", "a"), ("a", "service"),
    ])
    assert result["dependency_hops"] == {"a": 1}
    assert result["cycle_detected"] is True
    assert result["topology_state"] == "UNKNOWN"
    assert result["live_remediation_authorized"] is False


def test_dependency_paths_provide_a_deterministic_shortest_witness():
    result = preview("service", ["service", "a", "b", "db"], [
        ("service", "b"), ("b", "db"), ("service", "a"), ("a", "db"),
    ])
    assert result["dependency_paths"] == {
        "a": ["service", "a"],
        "b": ["service", "b"],
        "db": ["service", "a", "db"],
    }
    assert result["dependency_hops"]["db"] == len(result["dependency_paths"]["db"]) - 1
    assert result["canonical_cmdb_verified"] is False


def test_direct_path_wins_over_longer_path():
    result = preview("service", ["service", "a", "db"], [
        ("service", "a"), ("a", "db"), ("service", "db"),
    ])
    assert result["dependency_paths"]["db"] == ["service", "db"]
    assert result["dependency_hops"]["db"] == 1


def test_cycle_path_witness_does_not_imply_verified_topology():
    result = preview("service", ["service", "a"], [
        ("service", "a"), ("a", "service"),
    ])
    assert result["dependency_paths"] == {"a": ["service", "a"]}
    assert result["topology_state"] == "UNKNOWN"
    assert result["authoritative"] is False


def test_direct_and_indirect_dependencies_are_disjoint_and_complete():
    result = preview("service", ["service", "app", "db", "cache", "unrelated"], [
        ("service", "app"), ("app", "db"), ("service", "cache"),
    ])
    assert result["direct_dependency_ids"] == ["app", "cache"]
    assert result["indirect_dependency_ids"] == ["db"]
    assert set(result["direct_dependency_ids"]).isdisjoint(result["indirect_dependency_ids"])
    assert sorted(result["direct_dependency_ids"] + result["indirect_dependency_ids"]) == result["dependency_ids"]
    assert result["dependency_hops"] == {"app": 1, "cache": 1, "db": 2}


def test_direct_edge_overrides_indirect_route_classification():
    result = preview("service", ["service", "app", "db"], [
        ("service", "app"), ("app", "db"), ("service", "db"),
    ])
    assert result["direct_dependency_ids"] == ["app", "db"]
    assert result["indirect_dependency_ids"] == []
    assert result["dependency_paths"]["db"] == ["service", "db"]


def test_self_loop_is_unknown_without_self_dependency():
    result = preview("service", ["service"], [("service", "service")])
    assert result["cycle_detected"] is True
    assert result["topology_state"] == "UNKNOWN"
    assert result["dependency_ids"] == []
    assert result["direct_dependency_ids"] == []
    assert result["indirect_dependency_ids"] == []
    assert result["live_remediation_authorized"] is False


def test_failed_ci_reverse_traversal_finds_possible_consumers():
    result = preview_upstream_dependents(
        "db", ["service", "app", "db", "unrelated"],
        [("service", "app"), ("app", "db")],
    )
    assert result["possible_dependent_ids"] == ["app", "service"]
    assert result["dependent_hops"] == {"app": 1, "service": 2}
    assert result["dependent_paths"]["service"] == ["db", "app", "service"]
    assert result["canonical_cmdb_verified"] is False
    assert result["authoritative"] is False
    assert result["live_remediation_authorized"] is False


def test_reverse_traversal_does_not_include_downstream_dependencies():
    result = preview_upstream_dependents(
        "app", ["service", "app", "db"],
        [("service", "app"), ("app", "db")],
    )
    assert result["possible_dependent_ids"] == ["service"]
    assert result["dependent_paths"] == {"service": ["app", "service"]}


def test_reverse_traversal_missing_endpoint_is_unknown():
    result = preview_upstream_dependents(
        "db", ["service", "db"],
        [("service", "db"), ("missing", "db")],
    )
    assert result["possible_dependent_ids"] == ["service"]
    assert result["topology_state"] == "UNKNOWN"
    assert result["unresolved_edge_detected"] is True


def test_reverse_traversal_rejects_malformed_edge():
    with pytest.raises(ValueError):
        preview_upstream_dependents("db", ["db"], [("missing", " bad")])


def test_reverse_traversal_cycle_is_unknown():
    result = preview_upstream_dependents(
        "db", ["db", "app"],
        [("app", "db"), ("db", "app")],
    )
    assert result["cycle_detected"] is True
    assert result["topology_state"] == "UNKNOWN"
    assert result["persisted"] is False


def test_dependency_path_dictionary_is_materialized_for_empty_graph():
    result = preview("service", ["service"], [])
    assert result["dependency_paths"] == {}
    assert result["dependency_hops"] == {}
    assert result["direct_dependency_ids"] == []
    assert result["indirect_dependency_ids"] == []
    assert result["topology_state"] == "CALLER_SUPPLIED_PREVIEW"


def test_maximum_bounded_chain_is_iterative_and_paths_are_consistent():
    nodes = [f"ci-{index:03d}" for index in range(200)]
    edges = list(zip(nodes, nodes[1:]))
    result = preview(nodes[0], nodes, edges)
    assert result["dependency_count"] == 199
    assert result["dependency_hops"][nodes[-1]] == 199
    assert result["dependency_paths"][nodes[-1]] == nodes
    assert result["direct_dependency_ids"] == [nodes[1]]
    assert len(result["indirect_dependency_ids"]) == 198
    assert result["topology_state"] == "CALLER_SUPPLIED_PREVIEW"
    assert result["live_remediation_authorized"] is False


def test_reverse_maximum_bounded_chain_is_iterative():
    nodes = [f"ci-{index:03d}" for index in range(200)]
    edges = list(zip(nodes, nodes[1:]))
    result = preview_upstream_dependents(nodes[-1], nodes, edges)
    assert result["possible_dependent_count"] == 199
    assert result["dependent_hops"][nodes[0]] == 199
    assert result["dependent_paths"][nodes[0]] == list(reversed(nodes))
    assert result["authoritative"] is False


def test_dense_duplicate_edges_remain_bounded_and_deterministic():
    nodes = ["service", "app"]
    edges = [("service", "app")] * 1000
    result = preview("service", nodes, edges)
    assert result["dependency_count"] == 1
    assert result["dependency_paths"] == {"app": ["service", "app"]}
    assert result["topology_state"] == "CALLER_SUPPLIED_PREVIEW"
