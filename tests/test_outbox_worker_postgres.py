"""Disposable PostgreSQL worker identity qualification; no HTTP traffic."""
import os
from uuid import uuid4

import asyncpg
import pytest


@pytest.mark.asyncio
async def test_worker_identity_and_concurrent_claims():
    if os.getenv("GAMMA_TEST_DISPOSABLE") != "1":
        pytest.skip("Disposable database required")
    admin_url = os.environ["GAMMA_WORKER_ADMIN_DSN"]
    a_url = os.environ["GAMMA_WORKER_A_DSN"]
    b_url = os.environ["GAMMA_WORKER_B_DSN"]
    admin = await asyncpg.connect(admin_url)
    connections = []
    ids = [uuid4(), uuid4()]
    tenants = [uuid4(), uuid4()]
    try:
        for url in (a_url, a_url, b_url):
            connections.append(await asyncpg.connect(url))
        a, competitor, b = connections
        names = [await c.fetchval("SELECT session_user") for c in (a, b)]
        assert names[0] != names[1]
        for name, tenant, row in zip(names, tenants, ids):
            await admin.execute("INSERT INTO public.outbox_worker_identity VALUES ($1::name,$2)", name, tenant)
            await admin.execute("""
                INSERT INTO public.integration_outbox
                (id,tenant_id,event_type,aggregate_id,payload)
                VALUES ($1,$2,'test','synthetic','{}'::jsonb)
            """, row, tenant)
        async with a.transaction():
            await a.fetchval("SELECT set_config('app.tenant_id',$1,true)", str(tenants[1]))
            assert await a.fetchval("SELECT id FROM integration_outbox WHERE id=$1", ids[1]) is None
            assert await a.fetchval("SELECT id FROM integration_outbox WHERE id=$1 FOR UPDATE SKIP LOCKED", ids[0]) == ids[0]
            async with competitor.transaction():
                assert await competitor.fetchval("SELECT id FROM integration_outbox WHERE id=$1 FOR UPDATE SKIP LOCKED", ids[0]) is None
            assert await b.fetchval("SELECT id FROM integration_outbox WHERE id=$1 FOR UPDATE SKIP LOCKED", ids[1]) == ids[1]
        assert await competitor.fetchval("SELECT id FROM integration_outbox WHERE id=$1 FOR UPDATE SKIP LOCKED", ids[0]) == ids[0]
        for statement in (
            "UPDATE integration_outbox SET payload='{}' WHERE id=$1",
            "UPDATE integration_outbox SET tenant_id=tenant_id WHERE id=$1",
            "DELETE FROM integration_outbox WHERE id=$1",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await a.execute(statement, ids[0])
        assert await a.execute("UPDATE integration_outbox SET attempts=1 WHERE id=$1", ids[0]) == "UPDATE 1"
    finally:
        for c in connections:
            await c.close()
        await admin.execute("DELETE FROM public.integration_outbox WHERE id=ANY($1::uuid[])", ids)
        await admin.execute("DELETE FROM public.outbox_worker_identity WHERE tenant_id=ANY($1::uuid[])", tenants)
        await admin.close()
