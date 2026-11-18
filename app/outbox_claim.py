"""Offline design for tenant-bound Outbox claims.

No HTTP dispatch, no startup wiring, no production role provisioning.
A worker database identity must be bound to one tenant by DBA-controlled
policy independently of the caller-settable tenant GUC.
"""
from uuid import UUID
from datetime import datetime

from sqlalchemy import or_, select

from app.models import OutboxEvent


def claim_statement(tenant_id: UUID, now: datetime, max_attempts: int = 10):
    if not isinstance(tenant_id, UUID) or tenant_id.int == 0:
        raise ValueError("A nonzero tenant UUID is required")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    if not 1 <= max_attempts <= 10:
        raise ValueError("Invalid retry budget")
    return (
        select(OutboxEvent)
        .where(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.published_at.is_(None),
            OutboxEvent.attempts < max_attempts,
            or_(OutboxEvent.next_attempt_at.is_(None),
                OutboxEvent.next_attempt_at <= now),
        )
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
