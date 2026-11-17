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
