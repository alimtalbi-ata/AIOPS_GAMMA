"""Offline, deny-by-default evidence snapshot intake for shadow investigations.

The caller supplies an immutable synthetic snapshot and explicit tenant grants.
No external connectors, persistence, remote reads, or live authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.reused.shadow_investigation import Evidence, Hypothesis, InvestigationInput, investigate_shadow


@dataclass(frozen=True)
class SyntheticSnapshot:
    snapshot_id: str
    tenant_id: str
    incident_id: str
    captured_at: datetime
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class SnapshotRequest:
    actor_id: str
    tenant_id: str
    incident_id: str
    allowed_tenants: tuple[str, ...]
    snapshot: SyntheticSnapshot
    hypotheses: tuple[Hypothesis, ...]
    as_of: datetime
    max_snapshot_age_seconds: int = 900


def investigate_snapshot(req: SnapshotRequest) -> dict:
    """Reject unauthorized or mismatched snapshots before RCA evaluation."""
    if type(req) is not SnapshotRequest:
        raise ValueError("Invalid snapshot request")
    if any(type(v) is not str or not v.strip() for v in (
            req.actor_id, req.tenant_id, req.incident_id)):
        raise ValueError("Missing identity")
    if (type(req.allowed_tenants) is not tuple
            or any(type(t) is not str or not t.strip() for t in req.allowed_tenants)
            or len(set(req.allowed_tenants)) != len(req.allowed_tenants)):
        raise ValueError("Invalid tenant grants")
    if req.tenant_id not in req.allowed_tenants:
        raise PermissionError("Tenant access denied")
    snapshot = req.snapshot
    if (type(snapshot) is not SyntheticSnapshot
            or type(snapshot.snapshot_id) is not str or not snapshot.snapshot_id.strip()
            or type(snapshot.tenant_id) is not str
            or type(snapshot.incident_id) is not str
            or snapshot.tenant_id != req.tenant_id
            or snapshot.incident_id != req.incident_id):
        raise ValueError("Snapshot identity mismatch")
    if (type(req.as_of) is not datetime or req.as_of.tzinfo is None
            or req.as_of.utcoffset() is None
            or type(snapshot.captured_at) is not datetime
            or snapshot.captured_at.tzinfo is None
            or snapshot.captured_at.utcoffset() is None
            or type(req.max_snapshot_age_seconds) is not int
            or req.max_snapshot_age_seconds < 1):
        raise ValueError("Invalid snapshot freshness policy")
    age = (req.as_of - snapshot.captured_at).total_seconds()
    if not 0 <= age <= req.max_snapshot_age_seconds:
        raise ValueError("Snapshot outside freshness window")
    if type(snapshot.evidence) is not tuple or type(req.hypotheses) is not tuple:
        raise ValueError("Invalid snapshot collections")
    result = investigate_shadow(InvestigationInput(
        tenant_id=req.tenant_id,
        incident_id=req.incident_id,
        hypotheses=req.hypotheses,
        evidence=snapshot.evidence,
        as_of=req.as_of,
    ))
    return {
        "snapshot_id": snapshot.snapshot_id,
        "actor_id": req.actor_id,
        "tenant_id": req.tenant_id,
        "incident_id": req.incident_id,
        "mode": "synthetic_shadow",
        "investigation": result,
        "grant_origin": "CALLER_DECLARED_SYNTHETIC",
        "authoritative": False,
        "live_execution_authorized": False,
        "connectors_invoked": False,
        "itsm_mutations_performed": False,
    }
