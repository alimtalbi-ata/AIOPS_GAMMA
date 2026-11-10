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
