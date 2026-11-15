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
