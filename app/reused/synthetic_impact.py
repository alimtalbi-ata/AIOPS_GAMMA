"""UC04: conservative, caller-supplied CMDB graph preview; never a canonical Twin read.

Edges point from an affected CI to a dependent CI. Missing or stale graph
coverage is explicitly UNKNOWN, not evidence that no other CIs are affected.
"""
from collections import deque
from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DependencyEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upstream_ci: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    dependent_ci: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")


class ImpactPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    root_ci: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    observed_at: datetime
    edges: list[DependencyEdge] = Field(default_factory=list, max_length=500)
    graph_complete: bool = False

    @model_validator(mode="after")
    def timezone_required(self):
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("Graph observation must be timezone-aware")
        return self


def preview_impact(req: ImpactPreviewRequest, authorized_tenant: UUID, *,
                   now: datetime | None = None, max_age_seconds: int = 3600) -> dict:
    if not isinstance(req, ImpactPreviewRequest) or not isinstance(authorized_tenant, UUID):
        raise ValueError("Invalid impact request or authorized tenant")
    # Reject post-validation mutation of graph edges, CI identity or timestamp.
    req = ImpactPreviewRequest.model_validate(req.model_dump())
    if req.tenant_id != authorized_tenant:
        raise PermissionError("Cross-tenant CMDB preview rejected")
    if not isinstance(max_age_seconds, int) or isinstance(max_age_seconds, bool) or not 1 <= max_age_seconds <= 86400:
        raise ValueError("Invalid freshness bound")
    current = datetime.now(timezone.utc) if now is None else now
    if (not isinstance(current, datetime) or current.tzinfo is None
            or current.utcoffset() is None):
        raise ValueError("Current time must be timezone-aware")
    age = (current - req.observed_at).total_seconds()
    fresh = 0 <= age <= max_age_seconds
    adjacency: dict[str, set[str]] = {}
    for edge in req.edges:
        adjacency.setdefault(edge.upstream_ci, set()).add(edge.dependent_ci)
    visited = {req.root_ci}
    queue = deque([req.root_ci])
    while queue:
        for dependent in sorted(adjacency.get(queue.popleft(), ())):
            if dependent not in visited:
                visited.add(dependent)
                queue.append(dependent)
    verified = fresh and req.graph_complete
    return {
        "schema_version": "aiops.gamma.synthetic-impact-preview.v1",
        "tenant_id": str(authorized_tenant),
        "root_ci": req.root_ci,
        "candidate_affected_cis": sorted(visited),
        "candidate_count": len(visited),
        "graph_fresh": fresh,
        "graph_complete": req.graph_complete,
        "impact_state": "CANDIDATE_ONLY" if verified else "UNKNOWN",
        "canonical_cmdb_verified": False,
        "data_source": "caller_supplied_preview",
        "persisted": False,
        "live_remediation_authorized": False,
    }
