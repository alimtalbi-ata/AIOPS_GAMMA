"""Offline evidence graph derived from scoped telemetry, not causal proof."""
from datetime import datetime
from hashlib import sha256
import json
from uuid import UUID

from app.reused.telemetry_correlation import correlate_telemetry
from app.reused.unified_telemetry import TelemetryObservation


def build_evidence_graph(items: list[TelemetryObservation], *, tenant_id: UUID,
                         grants: frozenset[tuple[str, str]],
                         bindings: dict[tuple[str, str], str],
                         now: datetime, window_seconds: int = 120,
                         max_age_seconds: int = 300) -> dict:
    """Use server-owned grants/bindings; never accept a precomputed graph as proof."""
    result = correlate_telemetry(items, tenant_id=tenant_id, grants=grants,
                                 bindings=bindings, now=now,
                                 window_seconds=window_seconds,
                                 max_age_seconds=max_age_seconds)
    nodes = []
    for row in result["observations"]:
        canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
        node_id = "obs-" + sha256(canonical.encode("utf-8")).hexdigest()
        nodes.append({"id": node_id, "kind": "OBSERVATION", "observation": row})
    edges = []
    for candidate in result["candidates"]:
        edges.append({
            "from": nodes[candidate["sentinel_index"]]["id"],
            "to": nodes[candidate["arguslm_index"]]["id"],
            "directed": False,
            "relation": "TEMPORAL_PROXIMITY",
            "service_id": candidate["service_id"],
            "distance_seconds": candidate["distance_seconds"],
            "state": "UNVERIFIED",
        })
    return {
        "schema_version": "gamma.evidence.graph.preview.v1",
        "tenant_id": str(tenant_id),
        "nodes": nodes,
        "edges": edges,
        "excluded": result["excluded"],
        "duplicates": result["duplicates"],
        "candidate_count": result["candidate_count"],
        "truncated": result["truncated"],
        "window_seconds": window_seconds,
        "max_age_seconds": max_age_seconds,
        "source_authenticated": False,
        "causality_established": False,
        "incident_identity_verified": False,
        "persisted": False,
        "live_remediation_authorized": False,
    }
