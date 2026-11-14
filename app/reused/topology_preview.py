"""Bounded, caller-supplied service dependency preview (UC04).

Pure in-memory graph traversal. No canonical CMDB reads, network, writes or authority.
"""
from collections import deque

MAX_NODES = 200
MAX_EDGES = 1000
MAX_ID_LENGTH = 255


def _valid_id(value: object) -> bool:
    return (isinstance(value, str) and 1 <= len(value) <= MAX_ID_LENGTH
            and value == value.strip() and value.isprintable())


def preview_service_dependencies(
    service_id: str, nodes: list[str], edges: list[tuple[str, str]]
) -> dict:
    """Return transitive dependencies; edges point from consumer to dependency.

    Cycles and incomplete graphs are flagged as UNKNOWN, not treated as proof
    of healthy topology. Caller-supplied identifiers are never authenticated.
    """
    if (not _valid_id(service_id)
            or not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES
            or not isinstance(edges, list) or len(edges) > MAX_EDGES):
        raise ValueError("Invalid topology preview bounds")
    if (any(not _valid_id(node) for node in nodes)
            or len(set(nodes)) != len(nodes) or service_id not in nodes):
        raise ValueError("Invalid topology node identifiers")
    graph = {node: set() for node in nodes}
    incomplete = False
    for edge in edges:
        if (not isinstance(edge, (tuple, list)) or len(edge) != 2
                or any(not _valid_id(endpoint) for endpoint in edge)):
            raise ValueError("Invalid topology edge")
        source, target = edge
        if source not in graph or target not in graph:
            incomplete = True
            continue
        graph[source].add(target)

    # A node is gray only while its DFS frame is active. Keeping the
    # child iterator in each frame avoids false cycles from pending siblings.
    color: dict[str, int] = {service_id: 1}
    cyclic = False
    stack = [(service_id, iter(sorted(graph[service_id])))]
    while stack:
        node, children = stack[-1]
        child = next(children, None)
        if child is None:
            color[node] = 2
            stack.pop()
            continue
        if color.get(child) == 1:
            cyclic = True
        elif color.get(child) != 2:
            color[child] = 1
            stack.append((child, iter(sorted(graph[child]))))

    # Breadth-first traversal reports the minimum number of dependency edges
    # from the selected service. It is not a latency, risk or impact score.
    depths = {service_id: 0}
    # Sorted neighbors + FIFO traversal select a deterministic shortest witness.
    parents: dict[str, str] = {}
    queue = deque([service_id])
    while queue:
        node = queue.popleft()
        for child in sorted(graph[node]):
            if child not in depths:
                depths[child] = depths[node] + 1
                parents[child] = node
                queue.append(child)

    reachable = sorted(set(depths) - {service_id})
    direct = sorted(graph[service_id] - {service_id})
    indirect = sorted(set(reachable) - set(direct))
    paths = {
    for dependency in reachable:
        path = [dependency]
        while path[-1] != service_id:
            path.append(parents[path[-1]])
        paths[dependency] = list(reversed(path))

    return {
        "service_id": service_id,
        "dependency_ids": reachable,
        "dependency_count": len(reachable),
        "direct_dependency_ids": direct,
        "indirect_dependency_ids": indirect,
        "dependency_hops": {node: depths[node] for node in reachable},
        "dependency_paths": paths,
        "topology_state": "UNKNOWN" if cyclic or incomplete else "CALLER_SUPPLIED_PREVIEW",
        "cycle_detected": cyclic,
        "unresolved_edge_detected": incomplete,
        "data_source": "caller_supplied_preview",
        "canonical_cmdb_verified": False,
        "authoritative": False,
        "persisted": False,
        "live_remediation_authorized": False,
    }


def preview_upstream_dependents(
    failed_ci_id: str, nodes: list[str], edges: list[tuple[str, str]]
) -> dict:
    """Preview consumers reachable upstream of a caller-supplied failing CI.

    Input edges point from consumer to dependency. Reversing them finds
    possible affected consumers, not verified services or actual blast radius.
    """
    # Validate through the shared bounded graph boundary before reversing.
    # In particular, invalid edges must never be silently discarded.
    preview_service_dependencies(failed_ci_id, nodes, edges)
    reversed_edges = [(target, source) for source, target in edges]
    result = preview_service_dependencies(failed_ci_id, nodes, reversed_edges)
    return {
        "failed_ci_id": failed_ci_id,
        "possible_dependent_ids": result["dependency_ids"],
        "possible_dependent_count": result["dependency_count"],
        "dependent_hops": result["dependency_hops"],
        "dependent_paths": result["dependency_paths"],
        "topology_state": result["topology_state"],
        "cycle_detected": result["cycle_detected"],
        "unresolved_edge_detected": result["unresolved_edge_detected"],
        "data_source": result["data_source"],
        "canonical_cmdb_verified": False,
        "authoritative": False,
        "persisted": False,
        "live_remediation_authorized": False,
    }
