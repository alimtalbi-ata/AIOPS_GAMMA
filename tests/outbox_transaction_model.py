"""Offline-only transaction exercise. No network client or production entrypoint."""
from datetime import datetime, timezone

from app.outbox_claim import claim_statement


async def simulate_delivery(session, tenant_id, receiver, *, interrupt=False):
    """Receiver is a synthetic callback; transaction ownership stays with caller."""
    async with session.begin():
        event = await session.scalar(claim_statement(tenant_id, datetime.now(timezone.utc)))
        if event is None:
            return False
        if event.tenant_id != tenant_id:
            raise RuntimeError("Tenant mismatch")
        acknowledged = await receiver(str(event.tenant_id), str(event.id), event.payload)
        if interrupt:
            raise RuntimeError("Synthetic interruption before commit")
        if acknowledged is True:
            event.published_at = datetime.now(timezone.utc)
            event.next_attempt_at = None
            event.last_error = None
        else:
            event.attempts += 1
        return True
