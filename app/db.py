"""Lazy database sessions: read-only previews must not require a DB driver on import."""
from functools import lru_cache

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.settings import settings


@lru_cache(maxsize=1)
def get_session_factory():
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with get_session_factory()() as session:
        yield session


async def get_tenant_session(tenant_id):
    """Yield a session with transaction-local PostgreSQL RLS tenant context.

    The tenant value comes only from the verified Gateway Principal. SET LOCAL
    semantics prevent the value leaking across pooled connections.
    """
    from sqlalchemy import text

    async with get_session_factory()() as session:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        yield session
