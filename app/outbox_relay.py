"""At-least-once outbox relay.

One transaction per delivery attempt. The row is locked during the HTTP call,
so only deploy against a trusted low-latency internal receiver. The receiver
MUST deduplicate by X-Event-Id. No external endpoint is configured by default.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import or_, select

from app.db import session_factory
from app.models import OutboxEvent
from app.reused.redaction import redact_text

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 10


def retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(300, 2 ** min(attempts, 8)))


async def dispatch_once(client: httpx.AsyncClient, endpoint: str, token: str) -> bool:
    async with session_factory() as session:
        async with session.begin():
            now = datetime.now(timezone.utc)
            stmt = (
                select(OutboxEvent)
                .where(
                    OutboxEvent.published_at.is_(None),
                    OutboxEvent.attempts < MAX_ATTEMPTS,
                    or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
                )
                .order_by(OutboxEvent.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            event = await session.scalar(stmt)
            if event is None:
                return False
            try:
                response = await client.post(
                    endpoint,
                    json={
                        "event_id": str(event.id),
                        "tenant_id": str(event.tenant_id),
                        "event_type": event.event_type,
                        "aggregate_id": event.aggregate_id,
                        "payload": event.payload,
                    },
                    headers={"Authorization": f"Bearer {token}", "X-Event-Id": str(event.id)},
                    timeout=5.0,
                )
                response.raise_for_status()
                event.published_at = now
                event.last_error = None
            except (httpx.HTTPError, ValueError) as exc:
                event.attempts += 1
                event.next_attempt_at = now + retry_delay(event.attempts)
                event.last_error = (redact_text(str(exc)) or "")[:1000]
                log.warning("Outbox delivery failed for %s (attempt %s)", event.id, event.attempts)
            return True


async def main():
    endpoint = os.getenv("CORRELATION_WEBHOOK_URL", "")
    token = os.getenv("CORRELATION_WEBHOOK_TOKEN", "")
    if not endpoint.startswith("https://") or not token:
        raise RuntimeError("Set HTTPS CORRELATION_WEBHOOK_URL and CORRELATION_WEBHOOK_TOKEN")
    async with httpx.AsyncClient() as client:
        while True:
            worked = await dispatch_once(client, endpoint, token)
            if not worked:
                await asyncio.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
