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
        business_permissions=("alerts:ingest",),
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
        business_permissions=("alerts:ingest",),
    )
    assert await alerts(payload, principal, Session()) == {
        "id": str(event_id), "duplicate": True,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", [False, True])
async def test_concurrent_duplicate_insert_uses_rollback_and_rechecks_payload(monkeypatch, conflict):
    """Simulate a unique-key race: the competing transaction wins at flush."""
    from datetime import datetime, timezone
    from sqlalchemy.exc import IntegrityError
    from app.main import alerts
    from app.schemas import AlertPayload
    from app.security import Principal
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_alert_ingestion", True)
    payload = AlertPayload(
        external_event_id="evt-race", source="opensearch", service_name="checkout",
        severity="major", status="firing",
        observed_at=datetime(2026, 11, 15, tzinfo=timezone.utc),
    )
    winner_id = uuid4()

    class RacingSession:
        def __init__(self):
            self.lookups = 0
            self.rollbacks = 0
            self.outbox_writes = 0

        async def scalar(self, statement):
            self.lookups += 1
            if self.lookups == 1:
                return None
            winner_payload = payload.model_dump(mode="json")
            if conflict:
                winner_payload["severity"] = "critical"
            return SimpleNamespace(id=winner_id, payload=winner_payload)

        def add(self, row):
            from app.models import OutboxEvent
            if isinstance(row, OutboxEvent):
                self.outbox_writes += 1

        async def flush(self):
            raise IntegrityError("INSERT INTO integration_inbox", {}, Exception("unique violation"))

        async def rollback(self):
            self.rollbacks += 1

        async def commit(self):
            raise AssertionError("failed flush must not commit")

    session = RacingSession()
    principal = Principal(
        tenant_id=uuid4(), subject="user:test", actor_type="user",
        assertion_id="assertion-test-123", expires_at=2000000000,
        business_permissions=("alerts:ingest",),
    )
    if conflict:
        with pytest.raises(HTTPException) as exc:
            await alerts(payload, principal, session)
        assert exc.value.status_code == 409
    else:
        assert await alerts(payload, principal, session) == {
            "id": str(winner_id), "duplicate": True,
        }
    assert session.lookups == 2
    assert session.rollbacks == 1
    assert session.outbox_writes == 0


@pytest.mark.asyncio
async def test_new_alert_creates_tenant_scoped_inbox_and_outbox_in_one_commit(monkeypatch):
    """The successful path must preserve tenant, event type and identical payload."""
    from datetime import datetime, timezone
    from app.main import alerts
    from app.models import InboxEvent, OutboxEvent
    from app.schemas import AlertPayload
    from app.security import Principal
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_alert_ingestion", True)
    tenant = uuid4()
    payload = AlertPayload(
        external_event_id="evt-new", source="opensearch", service_name="checkout",
        severity="critical", status="firing",
        observed_at=datetime(2026, 11, 15, tzinfo=timezone.utc),
        evidence_refs=["otel:trace-1"],
    )

    class Session:
        def __init__(self):
            self.rows = []
            self.flushes = 0
            self.commits = 0

        async def scalar(self, statement):
            return None

        def add(self, row):
            self.rows.append(row)

        async def flush(self):
            self.flushes += 1
            for row in self.rows:
                if isinstance(row, InboxEvent):
                    row.id = uuid4()

        async def commit(self):
            self.commits += 1

    session = Session()
    principal = Principal(
        tenant_id=tenant, subject="user:test", actor_type="user",
        assertion_id="assertion-test-123", expires_at=2000000000,
        business_permissions=("alerts:ingest",),
    )
    result = await alerts(payload, principal, session)
    assert result["duplicate"] is False
    assert session.flushes == 1
    assert session.commits == 1
    assert len(session.rows) == 2
    inbox, outbox = session.rows
    assert isinstance(inbox, InboxEvent)
    assert isinstance(outbox, OutboxEvent)
    assert result["id"] == str(inbox.id)
    assert inbox.tenant_id == outbox.tenant_id == tenant
    assert inbox.external_event_id == "evt-new"
    assert inbox.source == "opensearch"
    assert outbox.event_type == "observability.alert.firing"
    assert outbox.aggregate_id == "checkout"
    assert inbox.payload == outbox.payload == payload.model_dump(mode="json")


@pytest.mark.asyncio
async def test_duplicate_lookup_is_scoped_to_authenticated_tenant_and_source(monkeypatch):
    """A duplicate lookup must never select an event from a different tenant."""
    from datetime import datetime, timezone
    from sqlalchemy.sql import operators
    from app.main import alerts
    from app.models import InboxEvent
    from app.schemas import AlertPayload
    from app.security import Principal
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_alert_ingestion", True)
    tenant = uuid4()
    payload = AlertPayload(
        external_event_id="evt-tenant", source="opensearch", service_name="checkout",
        severity="major", status="firing",
        observed_at=datetime(2026, 11, 15, tzinfo=timezone.utc),
    )
    event_id = uuid4()

    class Session:
        async def scalar(self, statement):
            assert statement.column_descriptions[0]["entity"] is InboxEvent
            predicates = list(statement.whereclause.clauses)
            filters = {}
            for predicate in predicates:
                assert predicate.operator is operators.eq
                filters[predicate.left.key] = predicate.right.value
            assert filters == {
                "tenant_id": tenant,
                "source": "opensearch",
                "external_event_id": "evt-tenant",
            }
            return SimpleNamespace(id=event_id, payload=payload.model_dump(mode="json"))

        def add(self, row):
            raise AssertionError("existing event must not trigger a write")

    principal = Principal(
        tenant_id=tenant, subject="user:test", actor_type="user",
        assertion_id="assertion-test-123", expires_at=2000000000,
        business_permissions=("alerts:ingest",),
    )
    assert await alerts(payload, principal, Session()) == {
        "id": str(event_id), "duplicate": True,
    }
