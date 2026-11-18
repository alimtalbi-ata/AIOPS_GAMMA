from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.reused.telemetry_evidence_graph import build_evidence_graph
from app.reused.unified_telemetry import TelemetryObservation

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
TENANT = uuid4()
GRANTS = frozenset({("sentinel", "s1"), ("arguslm", "a1")})
BINDINGS = {("sentinel", "s1"): "svc", ("arguslm", "a1"): "svc"}


def row(source, seconds=0, **changes):
    data = dict(tenant_id=TENANT, source=source,
                resource_id="s1" if source == "sentinel" else "a1",
                external_id="event", source_version="v1",
                observed_at=NOW-timedelta(seconds=seconds), fetched_at=NOW,
                metric="anomalies_total" if source == "sentinel" else "latency_ms",
                value=2)
    return TelemetryObservation(**(data | changes))


def graph(items, **changes):
    return build_evidence_graph(items, **(dict(tenant_id=TENANT,
        grants=GRANTS, bindings=BINDINGS, now=NOW) | changes))


def test_graph_references_and_provenance():
    result = graph([row("sentinel"), row("arguslm", 10)])
    ids = {node["id"] for node in result["nodes"]}
    assert len(ids) == 2
    edge, = result["edges"]
    assert {edge["from"], edge["to"]} == ids
    assert edge["directed"] is False
    assert edge["state"] == "UNVERIFIED"
    assert edge["distance_seconds"] == 10
    assert all(node["observation"]["source_version"] == "v1" for node in result["nodes"])
    for flag in ("source_authenticated", "causality_established",
                 "incident_identity_verified", "persisted", "live_remediation_authorized"):
        assert result[flag] is False


def test_determinism_and_duplicates():
    rows = [row("sentinel"), row("arguslm"), row("sentinel")]
    assert graph(rows) == graph(list(reversed(rows)))
    assert graph(rows)["duplicates"] == 1


def test_stale_kept_without_edges():
    result = graph([row("sentinel"), row("arguslm", 301)])
    assert len(result["nodes"]) == 2
    assert result["edges"] == []
    assert result["excluded"]["stale"] == 1


def test_cross_tenant_and_conflicts_fail_closed():
    with pytest.raises(PermissionError):
        graph([row("sentinel", tenant_id=uuid4())])
    with pytest.raises(ValueError):
        graph([row("sentinel"), row("sentinel", value=3)])


def test_no_mapping_no_edges():
    assert graph([row("sentinel"), row("arguslm")], bindings={})["edges"] == []


def test_truncation_visible():
    rows = [row(source, external_id=str(i)) for source in ("sentinel", "arguslm") for i in range(25)]
    result = graph(rows)
    assert len(result["edges"]) == 500
    assert result["candidate_count"] == 625
    assert result["truncated"] is True
