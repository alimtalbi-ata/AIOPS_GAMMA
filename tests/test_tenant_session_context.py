import os
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.db import bind_tenant_context


@pytest.mark.asyncio
async def test_context_rebound_and_pool_clean():
    if os.getenv("GAMMA_TEST_DISPOSABLE") != "1":
        pytest.skip("Disposable database required")
    engine = create_async_engine(os.environ["GAMMA_TEST_DATABASE_URL"], pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine)
    a, b = uuid4(), uuid4()
    query = text("SELECT NULLIF(current_setting('app.tenant_id', true), '')")
    try:
        async with factory() as session:
            bind_tenant_context(session, a)
            assert await session.scalar(query) == str(a)
            await session.commit()
            assert await session.scalar(query) == str(a)
            await session.rollback()
            assert await session.scalar(query) == str(a)
            with pytest.raises(RuntimeError):
                bind_tenant_context(session, b)
        async with factory() as session:
            assert await session.scalar(query) is None
        async with factory() as session:
            bind_tenant_context(session, b)
            assert await session.scalar(query) == str(b)
    finally:
        await engine.dispose()
