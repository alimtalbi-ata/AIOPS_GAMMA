"""Offline, deny-by-default evidence snapshot intake for shadow investigations.

The caller supplies an immutable synthetic snapshot and explicit tenant grants.
No external connectors, persistence, remote reads, or live authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
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
    expected_fingerprint_sha256: str | None = None


def snapshot_fingerprint(snapshot: SyntheticSnapshot) -> str:
    """Stable audit fingerprint of supplied metadata; NOT a provenance signature."""
    if type(snapshot) is not SyntheticSnapshot or type(snapshot.evidence) is not tuple:
        raise ValueError("Invalid snapshot")
    if type(snapshot.captured_at) is not datetime or snapshot.captured_at.tzinfo is None:
        raise ValueError("Invalid snapshot time")
    rows = []
    for item in snapshot.evidence:
        if type(item) is not Evidence or type(item.observed_at) is not datetime or item.observed_at.tzinfo is None:
            raise ValueError("Invalid evidence metadata")
        rows.append((item.ref, item.tenant_id, item.incident_id,
                     item.hypothesis_id, item.stance, item.observed_at.isoformat(),
                     item.source_verified, item.source_id))
    payload = (snapshot.snapshot_id, snapshot.tenant_id, snapshot.incident_id,
               snapshot.captured_at.isoformat(), tuple(sorted(rows)))
    return sha256(json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


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
    # A captured snapshot cannot contain observations from its own future.
    # Validate temporal coherence before evaluating or fingerprinting evidence.
    for item in snapshot.evidence:
        if (type(item) is not Evidence
                or type(item.observed_at) is not datetime
                or item.observed_at.tzinfo is None
                or item.observed_at.utcoffset() is None):
            raise ValueError("Invalid snapshot evidence timestamp")
        if item.observed_at > snapshot.captured_at:
            raise ValueError("Evidence newer than snapshot capture")
    fingerprint = snapshot_fingerprint(snapshot)
    expected = req.expected_fingerprint_sha256
    if expected is not None:
        if (type(expected) is not str or len(expected) != 64
                or any(ch not in '0123456789abcdef' for ch in expected)):
            raise ValueError('Invalid expected snapshot fingerprint')
        if fingerprint != expected:
            raise ValueError('Snapshot fingerprint mismatch')
    result = investigate_shadow(InvestigationInput(
        tenant_id=req.tenant_id,
        incident_id=req.incident_id,
        hypotheses=req.hypotheses,
        evidence=snapshot.evidence,
        as_of=req.as_of,
    ))
    return {
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_fingerprint_sha256": fingerprint,
        "fingerprint_scope": "CALLER_DECLARED_METADATA_ONLY",
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
