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


def test_mutated_evidence_timestamp_rejected_at_normalization_boundary():
    item = evidence()
    item.observed_at = datetime(2026, 11, 10, 12)
    with pytest.raises(ValidationError, match="observed_at requires timezone"):
        normalize([item], now=NOW)


def test_mutated_evidence_payload_limit_rejected_at_normalization_boundary():
    item = evidence()
    item.payload["text"] = "x" * 65537
    with pytest.raises(ValidationError, match="payload exceeds"):
        normalize([item], now=NOW)


def test_mutated_evidence_nan_rejected_at_normalization_boundary():
    item = evidence()
    item.payload["value"] = float("nan")
    with pytest.raises(ValidationError, match="finite JSON"):
        normalize([item], now=NOW)


def test_mutated_evidence_identity_rejected_at_normalization_boundary():
    item = evidence()
    item.source = ""
    with pytest.raises(ValidationError):
        normalize([item], now=NOW)


@pytest.mark.parametrize("invalid_age", [True, 60.5, "60"])
def test_evidence_normalization_rejects_invalid_freshness_types(invalid_age):
    with pytest.raises(ValueError, match="bounds"):
        normalize([evidence()], now=NOW, max_age_seconds=invalid_age)


@pytest.mark.parametrize("field", ["payload", "provenance"])
def test_mixed_json_object_keys_rejected_before_deterministic_hashing(field):
    with pytest.raises(ValidationError, match="JSON object keys"):
        evidence(**{field: {"valid": 1, 2: "invalid-key"}})


@pytest.mark.parametrize("field", ["payload", "provenance"])
def test_mutated_mixed_json_object_keys_rejected_at_normalization_boundary(field):
    item = evidence()
    getattr(item, field)[2] = "invalid-key"
    with pytest.raises(ValueError, match="JSON object keys"):
        normalize([item], now=NOW)


def test_evidence_payload_hash_is_independent_of_object_key_order():
    first = normalize([evidence(payload={"z": 1, "a": 2})], now=NOW)
    second = normalize([evidence(payload={"a": 2, "z": 1})], now=NOW)
    assert first == second
    assert first["items"][0]["integrity"] == "UNVERIFIED"


@pytest.mark.parametrize("field", ["payload", "provenance"])
def test_nested_non_string_json_keys_rejected_before_hashing(field):
    with pytest.raises(ValidationError, match="JSON object keys"):
        evidence(**{field: {"nested": [{"1": "valid", 1: "ambiguous"}]}})


@pytest.mark.parametrize("field", ["payload", "provenance"])
def test_mutated_nested_non_string_json_keys_rejected_at_boundary(field):
    item = evidence()
    getattr(item, field)["nested"] = [{"1": "valid", 1: "ambiguous"}]
    with pytest.raises(ValueError, match="JSON object keys"):
        normalize([item], now=NOW)


@pytest.mark.parametrize("field", ["payload", "provenance"])
def test_non_string_only_json_key_cannot_alias_string_key(field):
    with pytest.raises(ValidationError, match="JSON object keys"):
        evidence(**{field: {1: "value"}})


@pytest.mark.parametrize("field", ["payload", "provenance"])
def test_cyclic_json_container_rejected_at_construction(field):
    cyclic = {}
    cyclic["self"] = cyclic
    # Pydantic may reject recursive dict input before our model validator runs.
    with pytest.raises(ValidationError):
        evidence(**{field: cyclic})


@pytest.mark.parametrize("field", ["payload", "provenance"])
def test_excessively_nested_json_rejected_at_construction(field):
    nested = {"leaf": "ok"}
    for _ in range(66):
        nested = {"child": nested}
    # Pydantic may enforce its own recursion limit before model validation.
    with pytest.raises(ValidationError):
        evidence(**{field: nested})


def test_shared_noncyclic_json_subtree_is_allowed():
    shared = {"value": 1}
    result = normalize([evidence(payload={"a": shared, "b": shared})], now=NOW)
    assert result["items"][0]["integrity"] == "UNVERIFIED"


@pytest.mark.parametrize("field", ["payload", "provenance"])
def test_mutated_cyclic_json_rejected_before_model_dump(field):
    item = evidence()
    cyclic = {}
    cyclic["self"] = cyclic
    setattr(item, field, cyclic)
    with pytest.raises(ValueError, match="Cyclic JSON container"):
        normalize([item], now=NOW)


@pytest.mark.parametrize("field", ["payload", "provenance"])
def test_mutated_excessive_nesting_rejected_before_model_dump(field):
    item = evidence()
    nested = {"leaf": 1}
    for _ in range(66):
        nested = {"child": nested}
    setattr(item, field, nested)
    with pytest.raises(ValueError, match="JSON nesting exceeds"):
        normalize([item], now=NOW)


@pytest.mark.parametrize("field", ["tenant_id", "incident_id", "source", "external_id", "claim"])
@pytest.mark.parametrize("bad_value", [" padded ", "bad\\ud800value"])
def test_evidence_identity_rejects_noncanonical_unicode(field, bad_value):
    payload = evidence().model_dump()
    payload[field] = bad_value
    with pytest.raises(ValidationError):
        EvidenceInput.model_validate(payload)


@pytest.mark.parametrize("field", ["payload", "provenance"])
def test_evidence_json_rejects_unpaired_surrogate_values_and_keys(field):
    for value in [{"proof": "bad\\ud800value"}, {"bad\\ud800key": "value"}]:
        payload = evidence().model_dump()
        payload[field] = value
        with pytest.raises(ValidationError, match="surrogate"):
            EvidenceInput.model_validate(payload)


@pytest.mark.parametrize("field", ["payload", "provenance"])
def test_evidence_direct_normalize_rejects_mutated_surrogate(field):
    item = evidence()
    setattr(item, field, {"proof": "bad\\ud800value"})
    with pytest.raises(ValueError, match="surrogate"):
        normalize([item], now=NOW)


@pytest.mark.parametrize("field", ["tenant_id", "incident_id", "source", "external_id", "claim"])
@pytest.mark.parametrize("control", ["\\x00", "\\x1f", "\\x7f"])
def test_evidence_identity_rejects_embedded_control_characters(field, control):
    payload = evidence().model_dump()
    payload[field] = "safe" + control + "suffix"
    with pytest.raises(ValidationError, match="canonical printable"):
        EvidenceInput.model_validate(payload)


def test_direct_normalization_rejects_mutated_control_character_identity():
    item = evidence()
    item.external_id = "evt\\x00forged"
    with pytest.raises(ValidationError, match="canonical printable"):
        normalize([item], now=NOW)
