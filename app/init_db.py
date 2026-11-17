"""POC-only database bootstrap; production must use reviewed Alembic migrations.

Do not import or connect to a database at module import time.
"""
import asyncio

from app.db import get_session_factory
from app.models import Base


async def main():
    # Explicit POC invocation only. The lazy session factory owns the engine.
    engine = get_session_factory().kw["bind"]
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()
        get_session_factory.cache_clear()


if __name__ == "__main__":
    asyncio.run(main())
