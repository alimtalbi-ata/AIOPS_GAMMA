"""Opt-in behavioral RLS checks against a disposable migrated PostgreSQL database."""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update, delete, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import InboxEvent, OutboxEvent, ServiceBinding, Evidence


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [InboxEvent, OutboxEvent, ServiceBinding, Evidence])
async def test_rls_crud_isolation(model):
    url = os.getenv("GAMMA_TEST_DATABASE_URL")
    if not url or os.getenv("GAMMA_TEST_DISPOSABLE") != "1":
        pytest.skip("Explicit disposable PostgreSQL opt-in required")
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    table = model.__table__
    a, b, row_id = uuid4(), uuid4(), uuid4()
    marker = str(row_id)
    fields = {
        InboxEvent: dict(source="test", external_event_id=marker, payload={}),
        OutboxEvent: dict(event_type="test", aggregate_id=marker, payload={}),
        ServiceBinding: dict(cmdb_service_id=uuid4(), otel_service_name=marker, environment="test"),
        Evidence: dict(incident_id=marker, investigation_id=uuid4(), source_type="logs",
                       source_ref="synthetic", observed_at=datetime.now(timezone.utc)),
    }[model]
    seeded = False

    async def context(connection, tenant):
        await connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                                 {"tenant": str(tenant)})

    query = select(table.c.id).where(table.c.id == row_id)
    try:
        async with engine.begin() as conn:
            assert await conn.scalar(text("""
                SELECT NOT r.rolsuper AND NOT r.rolbypassrls
                    AND c.relrowsecurity AND c.relforcerowsecurity
                    AND NOT pg_has_role(current_user, c.relowner, 'MEMBER')
                FROM pg_roles r CROSS JOIN pg_class c
                WHERE r.rolname=current_user AND c.oid=to_regclass(:table)
            """), {"table": "public." + table.name}) is True
            await context(conn, a)
            await conn.execute(insert(table).values(id=row_id, tenant_id=a, **fields))
            assert await conn.scalar(query) == row_id
        seeded = True
        async with engine.begin() as conn:
            assert await conn.scalar(query) is None
            await context(conn, b)
            assert await conn.scalar(query) is None
            assert (await conn.execute(update(table).where(table.c.id == row_id)
                                        .values(tenant_id=b))).rowcount == 0
            assert (await conn.execute(delete(table).where(table.c.id == row_id))).rowcount == 0
            with pytest.raises(DBAPIError) as exc:
                async with conn.begin_nested():
                    await conn.execute(insert(table).values(id=uuid4(), tenant_id=a, **fields))
            assert exc.value.orig.sqlstate == "42501"
        async with engine.begin() as conn:
            await context(conn, a)
            assert await conn.scalar(query) == row_id
            with pytest.raises(DBAPIError) as exc:
                async with conn.begin_nested():
                    await conn.execute(update(table).where(table.c.id == row_id).values(tenant_id=b))
            assert exc.value.orig.sqlstate == "42501"
        async with engine.connect() as conn:
            transaction = await conn.begin()
            await context(conn, a)
            await transaction.rollback()
            assert await conn.scalar(query) is None
    finally:
        try:
            if seeded:
                async with engine.begin() as conn:
                    await context(conn, a)
                    await conn.execute(delete(table).where(table.c.id == row_id))
        finally:
            await engine.dispose()
