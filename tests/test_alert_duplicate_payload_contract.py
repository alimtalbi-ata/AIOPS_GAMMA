"""P3 inbox idempotency: a reused event key cannot silently change event content."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.main import alert_duplicate_response


def test_exact_retry_returns_original_inbox_event_id():
    event_id = uuid4()
    payload = {"source": "opensearch", "severity": "major"}
    previous = SimpleNamespace(id=event_id, payload=payload)
    assert alert_duplicate_response(previous, dict(payload)) == {
        "id": str(event_id), "duplicate": True,
    }


@pytest.mark.parametrize("changed", [
    {"severity": "critical"},
    {"source": "other"},
    {"unexpected": True},
])
def test_conflicting_retry_is_rejected(changed):
    previous = SimpleNamespace(
        id=uuid4(), payload={"source": "opensearch", "severity": "major"},
    )
    payload = dict(previous.payload)
    payload.update(changed)
    with pytest.raises(HTTPException) as exc:
        alert_duplicate_response(previous, payload)
    assert exc.value.status_code == 409
