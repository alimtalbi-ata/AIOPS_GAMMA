"""Atomic, shared replay reservation contract for signed gateway assertions.

Not wired to authentication until reviewed migration and gateway integration.
Never replace this with a process-local set: replicas must share replay state.
"""
import asyncio
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
    if (not isinstance(issuer, str) or not 1 <= len(issuer) <= 1024 or "\x00" in issuer
            or any(0xD800 <= ord(ch) <= 0xDFFF for ch in issuer)
            or not isinstance(assertion_id, str) or not 8 <= len(assertion_id) <= 128
            or not assertion_id.isascii()
            or any(not 33 <= ord(ch) <= 126 for ch in assertion_id)
            or type(expires_at) is not int or expires_at <= 0):
        raise ValueError("invalid replay reservation")
    # Validate timestamp conversion before any database interaction. Extremely
    # large integers can otherwise raise platform-dependent OverflowError.
    try:
        expiry_utc = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("invalid replay reservation") from exc
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
            "expires_at": expiry_utc,
        },
    )
    return result.scalar_one_or_none() is not None


async def consume_assertion_before_access(
    session: AsyncSession, *, issuer: str, assertion_id: str, expires_at: int
) -> bool:
    """Atomically reserve and COMMIT replay state before any protected work.

    False means duplicate assertion. A failed commit raises; never grant access.
    Use a dedicated short-lived session, not the handler's business transaction.
    This helper is NOT wired to authentication until DB migration is qualified.
    """
    try:
        reserved = await reserve_assertion_once(
            session, issuer=issuer, assertion_id=assertion_id, expires_at=expires_at
        )
        if reserved:
            await session.commit()
            return True
    except (Exception, asyncio.CancelledError):
        # Task cancellation must not silently leave an uncommitted reservation.
        await session.rollback()
        raise
    # A duplicate must roll back exactly once. Keep this outside the
    # exception handler so a rollback failure is never retried or masked.
    await session.rollback()
    return False


async def purge_expired_assertions(
    session: AsyncSession, *, batch_size: int = 500, grace_seconds: int = 120
) -> int:
    """Delete at most one bounded batch of expired replay rows.

    The grace window protects against small clock skew between API workers and
    PostgreSQL. Rows are eligible only when expires_at is older than database
    NOW() minus the grace window. SKIP LOCKED allows concurrent cleanup workers
    without waiting on each other. Caller should invoke this from a maintenance
    job, never on the authentication request path.
    """
    if (type(batch_size) is not int or not 1 <= batch_size <= 10_000
            or type(grace_seconds) is not int or not 60 <= grace_seconds <= 86_400):
        raise ValueError("invalid replay cleanup policy")
    try:
        result = await session.execute(
            text("""
                SELECT replay_maintenance.purge_expired(:batch_size, :grace_seconds)
            """),
            {"grace_seconds": grace_seconds, "batch_size": batch_size},
        )
        deleted = result.scalar_one_or_none()
        if type(deleted) is not int or deleted < 0 or deleted > batch_size:
            raise RuntimeError("invalid replay cleanup row count")
        await session.commit()
        return deleted
    except (Exception, asyncio.CancelledError):
        await session.rollback()
        raise
