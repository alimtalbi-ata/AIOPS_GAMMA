"""Exercise transaction model with disposable PostgreSQL and synthetic callback."""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models import OutboxEvent
from outbox_transaction_model import simulate_delivery


@pytest.mark.asyncio
async def test_delivery_rollback_then_replay():
    url = os.getenv("GAMMA_TEST_DATABASE_URL")
    if not url or os.getenv("GAMMA_TEST_DISPOSABLE") != "1":
        pytest.skip("Disposable PostgreSQL required")
    engine = create_async_engine(url)
    tenant, event_id = uuid4(), uuid4()
    effects = set()
    seeded = False
    from sqlalchemy import event
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def receiver(tenant_id, identity, payload):
        effects.add((tenant_id, identity))
        return True

    try:
        async with factory() as session:
            @event.listens_for(session.sync_session, "after_begin")
            def bind_context(session, transaction, connection):
                connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                                   {"tenant": str(tenant)})
            async with session.begin():
                session.add(OutboxEvent(id=event_id, tenant_id=tenant, event_type="test",
                                        aggregate_id="synthetic", payload={"synthetic": True}))
            seeded = True
            with pytest.raises(RuntimeError, match="Synthetic interruption"):
                await simulate_delivery(session, tenant, receiver, interrupt=True)
            async with session.begin():
                row = await session.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id))
                assert row.published_at is None
            assert await simulate_delivery(session, tenant, receiver)
            async with session.begin():
                row = await session.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id))
                assert row.published_at is not None
            assert effects == {(str(tenant), str(event_id))}
            assert not await simulate_delivery(session, tenant, receiver)
    finally:
        try:
            if seeded:
                async with engine.begin() as connection:
                    await connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                                             {"tenant": str(tenant)})
                    await connection.execute(text("DELETE FROM integration_outbox WHERE id=:id"),
                                             {"id": event_id})
        finally:
            await engine.dispose()
