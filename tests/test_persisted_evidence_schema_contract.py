"""P1 regression: persisted evidence inputs must be bounded before database writes."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import EvidenceIn


NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


def evidence(**overrides):
    values = {
        "investigation_id": "11111111-1111-4111-8111-111111111111",
        "source_type": "logs",
        "source_ref": "otel:trace-1",
        "summary": "Synthetic evidence",
        "observed_at": NOW,
    }
    values.update(overrides)
    return EvidenceIn(**values)


def test_bounded_valid_evidence_input():
    assert evidence(source_ref="x" * 512, summary="s" * 4096).source_type == "logs"


@pytest.mark.parametrize("invalid_ref", ["", " x", "x ", "x\n", "x\x00", "x" * 513])
def test_unbounded_or_noncanonical_evidence_reference_rejected(invalid_ref):
    with pytest.raises(ValidationError):
        evidence(source_ref=invalid_ref)


def test_oversized_evidence_summary_rejected():
    with pytest.raises(ValidationError):
        evidence(summary="x" * 4097)


def test_naive_persisted_evidence_timestamp_rejected():
    with pytest.raises(ValidationError):
        evidence(observed_at=datetime(2026, 11, 15, 12))
