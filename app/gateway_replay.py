"""Atomic, shared replay reservation contract for signed gateway assertions.

Not wired to authentication until reviewed migration and gateway integration.
Never replace this with a process-local set: replicas must share replay state.
"""
import hashlib
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def reserve_assertion_once(
    session: AsyncSession, *, issuer: str, assertion_id: str, expires_at: int
) -> bool:
    """Reserve issuer/jti once. Caller must COMMIT before protected access.

    Requires a reviewed database migration creating gateway_assertion_replay
    with assertion_digest as unique primary key. DB errors propagate closed.
    """
    if not issuer or not assertion_id or expires_at <= 0:
        raise ValueError("invalid replay reservation")
    digest = hashlib.sha256((issuer + "\x00" + assertion_id).encode()).hexdigest()
    result = await session.execute(
        text("""
            INSERT INTO gateway_assertion_replay (assertion_digest, expires_at)
            VALUES (:digest, :expires_at)
            ON CONFLICT (assertion_digest) DO NOTHING
            RETURNING assertion_digest
        """),
        {
            "digest": digest,
            "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc),
        },
    )
    return result.scalar_one_or_none() is not None
