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


@pytest.mark.asyncio
async def test_existing_conflicting_alert_never_writes_to_inbox_or_outbox(monkeypatch):
    from datetime import datetime, timezone
    from app.main import alerts
    from app.schemas import AlertPayload
    from app.security import Principal
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_alert_ingestion", True)
    tenant = uuid4()
    payload = AlertPayload(
        external_event_id="evt-1", source="opensearch", service_name="checkout",
        severity="critical", status="firing",
        observed_at=datetime(2026, 11, 15, tzinfo=timezone.utc),
    )
    existing = SimpleNamespace(
        id=uuid4(), payload={**payload.model_dump(mode="json"), "severity": "major"},
    )

    class Session:
        def __init__(self):
            self.writes = 0

        async def scalar(self, statement):
            return existing

        def add(self, row):
            self.writes += 1

        async def commit(self):
            self.writes += 1

    session = Session()
    principal = Principal(
        tenant_id=tenant, subject="user:test", actor_type="user",
        assertion_id="assertion-test-123", expires_at=2000000000,
    )
    with pytest.raises(HTTPException) as exc:
        await alerts(payload, principal, session)
    assert exc.value.status_code == 409
    assert session.writes == 0


@pytest.mark.asyncio
async def test_exact_duplicate_alert_never_creates_another_outbox_event(monkeypatch):
    from datetime import datetime, timezone
    from app.main import alerts
    from app.schemas import AlertPayload
    from app.security import Principal
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_alert_ingestion", True)
    payload = AlertPayload(
        external_event_id="evt-1", source="opensearch", service_name="checkout",
        severity="major", status="firing",
        observed_at=datetime(2026, 11, 15, tzinfo=timezone.utc),
    )
    event_id = uuid4()

    class Session:
        async def scalar(self, statement):
            return SimpleNamespace(id=event_id, payload=payload.model_dump(mode="json"))

        def add(self, row):
            raise AssertionError("duplicate must not create an outbox event")

        async def commit(self):
            raise AssertionError("duplicate must not commit")

    principal = Principal(
        tenant_id=uuid4(), subject="user:test", actor_type="user",
        assertion_id="assertion-test-123", expires_at=2000000000,
    )
    assert await alerts(payload, principal, Session()) == {
        "id": str(event_id), "duplicate": True,
    }
