"""P1 ingestion validation before inbox/outbox persistence."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import AlertPayload


def alert(**changes):
    values = {
        "external_event_id": "event-1",
        "source": "opensearch",
        "service_name": "checkout",
        "severity": "major",
        "status": "firing",
        "observed_at": datetime(2026, 11, 15, tzinfo=timezone.utc),
        "evidence_refs": ["otel:trace-1"],
    }
    values.update(changes)
    return AlertPayload(**values)


def test_valid_alert_evidence_bounds():
    assert len(alert(evidence_refs=["x" * 512] * 50).evidence_refs) == 50


@pytest.mark.parametrize("refs", [
    ["x" * 513], [""], ["valid"] * 51,
])
def test_invalid_alert_evidence_references_rejected(refs):
    with pytest.raises(ValidationError):
        alert(evidence_refs=refs)


def test_naive_alert_timestamp_rejected():
    with pytest.raises(ValidationError):
        alert(observed_at=datetime(2026, 11, 15))


def test_aware_alert_timestamp_accepted():
    assert alert().observed_at.utcoffset() is not None


@pytest.mark.parametrize("refs", [
    [" leading"], ["trailing "], ["line\nfeed"], ["null\x00byte"],
    ["delete\x7fchar"],
])
def test_noncanonical_alert_evidence_references_rejected(refs):
    with pytest.raises(ValidationError):
        alert(evidence_refs=refs)


@pytest.mark.parametrize("field", ["external_event_id", "source", "service_name"])
@pytest.mark.parametrize("bad_value", [" leading", "trailing ", "line\nfeed", "null\x00byte", "del\x7f"])
def test_noncanonical_alert_deduplication_and_aggregate_keys_rejected(field, bad_value):
    with pytest.raises(ValidationError):
        alert(**{field: bad_value})


@pytest.mark.parametrize("field,max_size", [
    ("external_event_id", 255), ("source", 100), ("service_name", 255),
])
def test_alert_identity_field_length_boundaries(field, max_size):
    assert getattr(alert(**{field: "x" * max_size}), field) == "x" * max_size
    with pytest.raises(ValidationError):
        alert(**{field: "x" * (max_size + 1)})


@pytest.mark.parametrize("unexpected", ["tenant_id", "actor_id", "admin_override"])
def test_unexpected_identity_and_authorization_fields_rejected(unexpected):
    with pytest.raises(ValidationError):
        alert(**{unexpected: "forged"})
