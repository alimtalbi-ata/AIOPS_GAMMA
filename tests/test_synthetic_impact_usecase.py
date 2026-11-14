"""UC04 synthetic CMDB impact: bounded graph and explicit uncertainty."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.reused.synthetic_impact import DependencyEdge, ImpactPreviewRequest, preview_impact

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


def request(*, tenant=TENANT, observed_at=NOW, complete=True, edges=None):
    if edges is None:
        edges = [("CI-A", "CI-B"), ("CI-B", "CI-C"), ("CI-C", "CI-A")]
    return ImpactPreviewRequest(
        tenant_id=tenant, root_ci="CI-A", observed_at=observed_at,
        graph_complete=complete,
        edges=[DependencyEdge(upstream_ci=a, dependent_ci=b) for a, b in edges],
    )


def test_transitive_impact_handles_cycle_without_claiming_authority():
    result = preview_impact(request(), TENANT, now=NOW)
    assert result["candidate_affected_cis"] == ["CI-A", "CI-B", "CI-C"]
    assert result["candidate_count"] == 3
    assert result["impact_state"] == "CANDIDATE_ONLY"
    assert result["canonical_cmdb_verified"] is False
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False


def test_incomplete_graph_does_not_imply_safe_blast_radius():
    result = preview_impact(request(complete=False), TENANT, now=NOW)
    assert result["candidate_count"] == 3
    assert result["impact_state"] == "UNKNOWN"


def test_stale_graph_downgrades_impact_to_unknown():
    result = preview_impact(request(observed_at=NOW - timedelta(hours=2)), TENANT, now=NOW)
    assert result["graph_fresh"] is False
    assert result["impact_state"] == "UNKNOWN"


def test_future_dated_graph_downgrades_impact_to_unknown():
    result = preview_impact(request(observed_at=NOW + timedelta(seconds=1)), TENANT, now=NOW)
    assert result["graph_fresh"] is False
    assert result["impact_state"] == "UNKNOWN"


def test_cross_tenant_graph_denied():
    with pytest.raises(PermissionError, match="Cross-tenant"):
        preview_impact(request(tenant=OTHER), TENANT, now=NOW)


def test_missing_edges_does_not_prove_no_dependents():
    result = preview_impact(request(edges=[], complete=False), TENANT, now=NOW)
    assert result["candidate_affected_cis"] == ["CI-A"]
    assert result["impact_state"] == "UNKNOWN"


def test_dependency_order_does_not_change_result():
    original = request()
    reversed_edges = request(edges=[
        (e.upstream_ci, e.dependent_ci) for e in reversed(original.edges)
    ])
    assert preview_impact(original, TENANT, now=NOW) == preview_impact(reversed_edges, TENANT, now=NOW)


def test_invalid_freshness_bound_rejected():
    with pytest.raises(ValueError, match="freshness"):
        preview_impact(request(), TENANT, now=NOW, max_age_seconds=0)


def test_mutated_graph_tenant_denied_at_preview_boundary():
    req = request()
    req.tenant_id = OTHER
    with pytest.raises(PermissionError, match="Cross-tenant"):
        preview_impact(req, TENANT, now=NOW)


def test_mutated_graph_edge_rejected_at_preview_boundary():
    from pydantic import ValidationError
    req = request()
    req.edges[0].dependent_ci = " "
    with pytest.raises(ValidationError):
        preview_impact(req, TENANT, now=NOW)


def test_mutated_graph_timestamp_rejected_at_preview_boundary():
    from pydantic import ValidationError
    req = request()
    req.observed_at = datetime(2026, 11, 14, 12)
    with pytest.raises(ValidationError, match="Graph observation"):
        preview_impact(req, TENANT, now=NOW)


def test_invalid_authorized_tenant_type_rejected():
    with pytest.raises(ValueError, match="authorized tenant"):
        preview_impact(request(), str(TENANT), now=NOW)


@pytest.mark.parametrize("invalid_age", [True, 1.5, "3600"])
def test_invalid_freshness_bound_types_rejected(invalid_age):
    with pytest.raises(ValueError, match="freshness"):
        preview_impact(request(), TENANT, now=NOW, max_age_seconds=invalid_age)


@pytest.mark.parametrize("invalid_now", [
    "", "2026-11-14T12:00:00Z", 0, False, [],
    datetime(2026, 11, 14, 12),
])
def test_invalid_supplied_clock_fails_closed(invalid_now):
    with pytest.raises(ValueError, match="Current time must be timezone-aware"):
        preview_impact(request(), TENANT, now=invalid_now)


def test_explicit_timezone_aware_clock_preserves_freshness():
    from datetime import timedelta
    offset_now = NOW.astimezone(timezone(timedelta(hours=5, minutes=30)))
    result = preview_impact(request(), TENANT, now=offset_now)
    assert result["graph_fresh"] is True
    assert result["impact_state"] == "CANDIDATE_ONLY"
    assert result["canonical_cmdb_verified"] is False
