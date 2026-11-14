"""Bounded, caller-supplied service dependency preview (UC04).

Pure in-memory graph traversal. No canonical CMDB reads, network, writes or authority.
"""
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
