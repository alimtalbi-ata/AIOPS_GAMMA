from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from app.reused.evidence import EvidenceInput, normalize

NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)


def evidence(**overrides):
    fields = dict(tenant_id="tenant-a", incident_id="inc-1", source="otel",
                  external_id="evt-1", claim="disk unhealthy", observed_at=NOW,
                  payload={"value": 1})
    fields.update(overrides)
    return EvidenceInput(**fields)


def test_fresh_evidence_is_not_authenticated():
    result = normalize([evidence()], now=NOW)
    assert result["items"][0]["freshness"] == "FRESH"
    assert result["items"][0]["integrity"] == "UNVERIFIED"
    assert result["live_remediation_authorized"] is False
    assert result["persisted"] is False


def test_stale_and_future_evidence_unknown():
    for when in (NOW - timedelta(hours=2), NOW + timedelta(seconds=1)):
        result = normalize([evidence(observed_at=when)], now=NOW)
        assert result["items"][0]["state"] == "UNKNOWN"


def test_duplicate_source_event_deduplicated():
    result = normalize([evidence(), evidence()], now=NOW)
    assert result["duplicates"] == 1
    assert len(result["items"]) == 1


def test_tenant_isolation():
    result = normalize([evidence(), evidence(tenant_id="tenant-b")], now=NOW)
    assert len(result["items"]) == 2


def test_conflicting_payloads_do_not_produce_verified_state():
    result = normalize([evidence(), evidence(source="prom", external_id="evt-2", payload={"value": 0})], now=NOW)
    assert all(row["state"] == "UNKNOWN" for row in result["items"])


def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError):
        evidence(observed_at=datetime(2026, 11, 10, 12))


def test_bounds_and_naive_now_rejected():
    with pytest.raises(ValueError):
        normalize([], now=NOW)
    with pytest.raises(ValueError):
        normalize([evidence()], now=NOW, max_age_seconds=0)
    with pytest.raises(ValueError):
        normalize([evidence()], now=NOW.replace(tzinfo=None))


def test_duplicate_event_with_changed_payload_is_not_silently_accepted():
    result = normalize([evidence(), evidence(payload={"value": 0})], now=NOW)
    assert all(row["state"] == "UNKNOWN" for row in result["items"])


def test_oversized_payload_rejected():
    with pytest.raises(ValidationError):
        evidence(payload={"text": "x" * 65536})


def test_oversized_provenance_rejected():
    with pytest.raises(ValidationError):
        evidence(provenance={"text": "x" * 8192})


def test_nan_payload_rejected():
    with pytest.raises(ValidationError):
        evidence(payload={"metric": float("nan")})


def test_provenance_fingerprint_is_deterministic_and_private():
    first = normalize([evidence(provenance={"origin": "otel", "trace": "private"})], now=NOW)
    second = normalize([evidence(provenance={"trace": "private", "origin": "otel"})], now=NOW)
    a, b = first["items"][0], second["items"][0]
    assert a["provenance_sha256"] == b["provenance_sha256"]
    assert len(a["provenance_sha256"]) == 64
    assert "provenance" not in a
    assert a["integrity"] == "UNVERIFIED"


def test_provenance_change_changes_fingerprint():
    first = normalize([evidence(provenance={"origin": "otel"})], now=NOW)
    second = normalize([evidence(provenance={"origin": "prom"})], now=NOW)
    assert first["items"][0]["provenance_sha256"] != second["items"][0]["provenance_sha256"]


def test_duplicate_event_with_conflicting_provenance_fails_closed():
    result = normalize([
        evidence(provenance={"collector": "otel-a"}),
        evidence(provenance={"collector": "otel-b"}),
    ], now=NOW)
    assert result["duplicates"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["state"] == "UNKNOWN"
    assert result["items"][0]["integrity"] == "UNVERIFIED"


def test_duplicate_event_with_equivalent_provenance_stays_unverified():
    result = normalize([
        evidence(provenance={"collector": "otel", "trace": "abc"}),
        evidence(provenance={"trace": "abc", "collector": "otel"}),
    ], now=NOW)
    assert result["duplicates"] == 1
    assert result["items"][0]["state"] == "UNVERIFIED"

def test_conflicting_duplicate_result_is_independent_of_arrival_order():
    first = evidence(payload={"status": "down"})
    second = evidence(payload={"status": "up"})
    forward = normalize([first, second], now=NOW)
    reverse = normalize([second, first], now=NOW)
    assert forward == reverse
    assert forward["duplicates"] == 1
    assert forward["items"][0]["state"] == "UNKNOWN"
    assert forward["items"][0]["integrity"] == "UNVERIFIED"


def test_freshness_inclusive_boundaries():
    at_now = evidence(observed_at=NOW)
    at_limit = evidence(external_id="evt-2", observed_at=NOW - timedelta(seconds=60))
    future = evidence(external_id="evt-3", observed_at=NOW + timedelta(microseconds=1))
    stale = evidence(external_id="evt-4", observed_at=NOW - timedelta(seconds=61))
    result = normalize([at_now, at_limit, future, stale], now=NOW, max_age_seconds=60)
    by_id = {entry["external_id"]: entry for entry in result["items"]}
    assert by_id["evt-1"]["freshness"] == "FRESH"
    assert by_id["evt-2"]["freshness"] == "FRESH"
    assert by_id["evt-3"]["freshness"] == "UNKNOWN"
    assert by_id["evt-4"]["freshness"] == "UNKNOWN"


def test_same_claim_with_different_payloads_is_unknown():
    one = evidence(external_id="evt-1", payload={"status": "down"})
    two = evidence(external_id="evt-2", payload={"status": "up"})
    result = normalize([one, two], now=NOW)
    assert len(result["items"]) == 2
    assert {entry["state"] for entry in result["items"]} == {"UNKNOWN"}
