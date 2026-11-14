"""Bounded, caller-supplied service dependency preview (UC04).

Pure in-memory graph traversal. No canonical CMDB reads, network, writes or authority.
"""
from collections import deque

MAX_NODES = 200
MAX_EDGES = 1000


def preview_service_dependencies(
    service_id: str, nodes: list[str], edges: list[tuple[str, str]]
) -> dict:
    """Return transitive dependencies; edges point from consumer to dependency.

    Cycles and incomplete graphs are flagged as UNKNOWN, not treated as proof
    of healthy topology. Caller-supplied identifiers are never authenticated.
    """
    if (not isinstance(service_id, str) or not service_id.strip()
            or not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES
            or not isinstance(edges, list) or len(edges) > MAX_EDGES):
        raise ValueError("Invalid topology preview bounds")
    if (any(not isinstance(node, str) or not node.strip() for node in nodes)
            or len(set(nodes)) != len(nodes) or service_id not in nodes):
        raise ValueError("Invalid topology node identifiers")
    graph = {node: set() for node in nodes}
    incomplete = False
    for edge in edges:
        if (not isinstance(edge, (tuple, list)) or len(edge) != 2
                or any(not isinstance(endpoint, str) or not endpoint.strip() for endpoint in edge)):
            raise ValueError("Invalid topology edge")
        source, target = edge
        if source not in graph or target not in graph:
            incomplete = True
            continue
        graph[source].add(target)

    # Iterative color DFS avoids recursion and detects reachable back-edges.
    color: dict[str, int] = {}
    cyclic = False
    stack = [(service_id, False)]
    while stack:
        node, leaving = stack.pop()
        if leaving:
            color[node] = 2
            continue
        if color.get(node) == 2:
            continue
        if color.get(node) == 1:
            cyclic = True
            continue
        color[node] = 1
        stack.append((node, True))
        for child in sorted(graph[node], reverse=True):
            if color.get(child) == 1:
                cyclic = True
            elif color.get(child) != 2:
                stack.append((child, False))

    reachable = sorted(set(color) - {service_id})
    return {
        "service_id": service_id,
        "dependency_ids": reachable,
        "dependency_count": len(reachable),
        "topology_state": "UNKNOWN" if cyclic or incomplete else "CALLER_SUPPLIED_PREVIEW",
        "cycle_detected": cyclic,
        "unresolved_edge_detected": incomplete,
        "data_source": "caller_supplied_preview",
        "canonical_cmdb_verified": False,
        "authoritative": False,
        "persisted": False,
        "live_remediation_authorized": False,
    }
