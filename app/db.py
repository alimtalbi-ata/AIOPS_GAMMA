"""Lazy database sessions: read-only previews must not require a DB driver on import."""
from functools import lru_cache
from uuid import UUID
from sqlalchemy import event, text

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.settings import settings


@lru_cache(maxsize=1)
def get_session_factory():
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with get_session_factory()() as session:
        yield session


def bind_tenant_context(session, tenant_id):
    """Bind one verified tenant to every outer transaction of this session."""
    if not isinstance(tenant_id, UUID) or tenant_id.int == 0:
        raise ValueError("Nonzero tenant UUID required")
    sync = session.sync_session
    if sync.in_transaction() or "gamma_tenant" in sync.info:
        raise RuntimeError("Tenant binding requires a fresh session")
    sync.info["gamma_tenant"] = tenant_id

    @event.listens_for(sync, "after_begin")
    def apply_context(_session, transaction, connection):
        if not transaction.nested:
            connection.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )


async def get_tenant_session(tenant_id):
    """Bind verified principal tenant across commits and rollbacks."""
    async with get_session_factory()() as session:
        bind_tenant_context(session, tenant_id)
        yield session
