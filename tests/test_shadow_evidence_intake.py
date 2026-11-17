"""Offline evidence intake isolation, freshness and safety tests."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.reused.shadow_evidence_intake import (
    SnapshotRequest, SyntheticSnapshot, investigate_snapshot, snapshot_fingerprint,
)
from app.reused.shadow_investigation import Evidence, Hypothesis

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)


def request():
    evidence = (
        Evidence("metric", "tenant-a", "inc-1", "db", "supports", NOW, True, "metrics"),
        Evidence("trace", "tenant-a", "inc-1", "db", "supports", NOW, True, "traces"),
    )
    snapshot = SyntheticSnapshot("snapshot-1", "tenant-a", "inc-1", NOW, evidence)
    return SnapshotRequest("actor-1", "tenant-a", "inc-1", ("tenant-a",),
                           snapshot, (Hypothesis("db", "Database saturation"),), NOW)


def test_snapshot_returns_review_only():
    result = investigate_snapshot(request())
    assert result["investigation"]["state"] == "REVIEW_CANDIDATE"
    assert result["investigation"]["selected_hypothesis_id"] == "db"
    assert result["grant_origin"] == "CALLER_DECLARED_SYNTHETIC"
    assert result["connectors_invoked"] is False
    assert result["live_execution_authorized"] is False
    assert result["itsm_mutations_performed"] is False


def test_unauthorized_tenant_rejected():
    with pytest.raises(PermissionError):
        investigate_snapshot(replace(request(), allowed_tenants=()))


@pytest.mark.parametrize("field,value", [
    ("tenant_id", "tenant-b"),
    ("incident_id", "inc-2"),
    ("snapshot_id", ""),
])
def test_snapshot_identity_mismatch_rejected(field, value):
    req = request()
    with pytest.raises(ValueError):
        investigate_snapshot(replace(req, snapshot=replace(req.snapshot, **{field: value})))


@pytest.mark.parametrize("delta", [-1, 901])
def test_snapshot_future_or_stale_rejected(delta):
    req = request()
    with pytest.raises(ValueError):
        investigate_snapshot(replace(req, snapshot=replace(
            req.snapshot, captured_at=NOW - timedelta(seconds=delta))))


def test_cross_tenant_evidence_causes_abstention():
    req = request()
    bad = replace(req.snapshot.evidence[1], tenant_id="tenant-b")
    result = investigate_snapshot(replace(req, snapshot=replace(
        req.snapshot, evidence=(req.snapshot.evidence[0], bad))))
    assert result["investigation"]["state"] == "ABSTAIN"
    assert ("trace", "IDENTITY_MISMATCH") in result["investigation"]["rejected_evidence"]


@pytest.mark.parametrize("changes", [
    {"actor_id": ""}, {"allowed_tenants": ("tenant-a", "tenant-a")},
    {"allowed_tenants": ["tenant-a"]}, {"max_snapshot_age_seconds": 0},
    {"max_snapshot_age_seconds": True},
])
def test_invalid_grants_and_policy_fail_closed(changes):
    with pytest.raises(ValueError):
        investigate_snapshot(replace(request(), **changes))


def test_pinned_fingerprint_accepts_unchanged_snapshot():
    req = request()
    pinned = replace(req, expected_fingerprint_sha256=snapshot_fingerprint(req.snapshot))
    result = investigate_snapshot(pinned)
    assert result["snapshot_fingerprint_sha256"] == pinned.expected_fingerprint_sha256


def test_pinned_fingerprint_detects_metadata_change():
    req = request()
    pinned = replace(req, expected_fingerprint_sha256=snapshot_fingerprint(req.snapshot))
    tampered = replace(pinned, snapshot=replace(req.snapshot, evidence=(
        replace(req.snapshot.evidence[0], source_id="different"),
        req.snapshot.evidence[1],
    )))
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        investigate_snapshot(tampered)


@pytest.mark.parametrize("expected", ["", "A" * 64, "0" * 63, "z" * 64, True])
def test_invalid_fingerprint_pins_fail_closed(expected):
    with pytest.raises(ValueError, match="Invalid expected"):
        investigate_snapshot(replace(request(), expected_fingerprint_sha256=expected))


def test_fingerprint_pin_does_not_override_tenant_denial():
    req = request()
    pinned = replace(req, expected_fingerprint_sha256=snapshot_fingerprint(req.snapshot),
                     allowed_tenants=())
    with pytest.raises(PermissionError):
        investigate_snapshot(pinned)


def test_evidence_newer_than_snapshot_capture_rejected():
    req = request()
    future_evidence = replace(req.snapshot.evidence[0], observed_at=NOW + timedelta(seconds=1))
    changed = replace(req, snapshot=replace(req.snapshot, evidence=(
        future_evidence, req.snapshot.evidence[1],
    )), as_of=NOW + timedelta(seconds=2))
    with pytest.raises(ValueError, match="newer than snapshot capture"):
        investigate_snapshot(changed)


def test_timezone_equivalent_evidence_timestamp_is_accepted():
    req = request()
    from datetime import timedelta as delta
    local_time = NOW.astimezone(timezone(delta(hours=2)))
    changed = replace(req, snapshot=replace(req.snapshot, evidence=(
        replace(req.snapshot.evidence[0], observed_at=local_time),
        req.snapshot.evidence[1],
    )))
    assert investigate_snapshot(changed)["investigation"]["state"] == "REVIEW_CANDIDATE"
