"""Synthetic topology join; adjacency is context, never proof of causation."""
from dataclasses import dataclass
from app.reused.shadow_inbox_rca import SyntheticInboxReceipt, evaluate_inbox_evidence
from app.reused.shadow_investigation import InvestigationInput


@dataclass(frozen=True)
class SyntheticDependency:
    tenant_id: str
    upstream: str
    downstream: str


def evaluate_topology_rca(receipt: SyntheticInboxReceipt, investigation: InvestigationInput,
                          service: str, dependencies: tuple[SyntheticDependency, ...]) -> dict:
    if type(service) is not str or not service.strip() or service != service.strip():
        raise ValueError("Invalid service")
    if type(dependencies) is not tuple or len(dependencies) > 500:
        raise ValueError("Invalid topology collection")
    report = evaluate_inbox_evidence(receipt, investigation)
    neighbors = set()
    for edge in dependencies:
        if type(edge) is not SyntheticDependency or edge.tenant_id != receipt.tenant_id:
            raise ValueError("Topology tenant mismatch")
        if any(type(v) is not str or not v.strip() or v != v.strip()
               for v in (edge.upstream, edge.downstream)):
            raise ValueError("Invalid topology reference")
        if edge.upstream == service:
            neighbors.add(("downstream", edge.downstream))
        if edge.downstream == service:
            neighbors.add(("upstream", edge.upstream))
    return {**report, "topology": {
        "service": service, "neighbors": tuple(sorted(neighbors)),
        "source_verified": False, "causation_established": False,
    }}
