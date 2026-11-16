"""At-least-once outbox relay.

One transaction per delivery attempt. The row is locked during the HTTP call,
so only deploy against a trusted low-latency internal receiver. The receiver
MUST deduplicate by X-Event-Id. No external endpoint is configured by default.
"""
import asyncio
import ipaddress
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy import or_, select

from app.db import get_session_factory
from app.models import OutboxEvent
from app.reused.redaction import redact_text

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 10


def valid_webhook_token(token: str) -> bool:
    """Accept only RFC 6750 bearer-token characters (no header delimiters)."""
    return (
        isinstance(token, str)
        and 1 <= len(token) <= 4096
        and re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token) is not None
    )


def retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(300, 2 ** min(attempts, 8)))


def valid_receiver_configuration(endpoint: str, token: str, allowed_host: str) -> bool:
    """Require a configured, exact receiver hostname at every dispatch boundary."""
    return (
        valid_webhook_endpoint(endpoint)
        and valid_webhook_token(token)
        and isinstance(allowed_host, str)
        and bool(allowed_host)
        and allowed_host == allowed_host.strip()
        and allowed_host.lower() == allowed_host
        and valid_webhook_endpoint(f"https://{allowed_host}/")
        and httpx.URL(endpoint).host == allowed_host
    )


def permanent_receiver_rejection(exc: Exception) -> bool:
    """Do not replay redirects or permanent 4xx; 408/425/429 remain retryable."""
    if not isinstance(exc, httpx.HTTPStatusError):
        return False
    status = exc.response.status_code
    return 300 <= status < 400 or (400 <= status < 500 and status not in (408, 425, 429))


def receiver_retry_delay(exc: Exception, attempts: int, *, now: datetime | None = None) -> timedelta:
    """Bound numeric or HTTP-date Retry-After for 429/503 to 300 seconds."""
    default = retry_delay(attempts)
    if not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code not in (429, 503):
        return default
    value = exc.response.headers.get("retry-after", "")
    if not value or len(value) > 128 or not value.isascii():
        return default
    if value.isdecimal():
        if len(value) > 6:
            return default
        seconds = int(value)
    else:
        try:
            deadline = parsedate_to_datetime(value)
            if deadline.tzinfo is None:
                return default
            seconds = (deadline - (now or datetime.now(timezone.utc))).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return default
    return timedelta(seconds=max(default.total_seconds(), min(seconds, 300)))


async def dispatch_once(client: httpx.AsyncClient, endpoint: str, token: str) -> bool:
    # Enforce the destination boundary even when called outside main().
    # Never query or claim an outbox row for an unsafe receiver.
    configured_endpoint = os.getenv("CORRELATION_WEBHOOK_URL", "")
    if (
        not valid_receiver_configuration(
            endpoint, token, os.getenv("CORRELATION_WEBHOOK_ALLOWED_HOST", "")
        )
        or endpoint != configured_endpoint
        or token != os.getenv("CORRELATION_WEBHOOK_TOKEN", "")
    ):
        raise ValueError("Invalid HTTPS outbox receiver configuration")
    async with get_session_factory()() as session:
        async with session.begin():
            now = datetime.now(timezone.utc)
            stmt = (
                select(OutboxEvent)
                .where(
                    OutboxEvent.published_at.is_(None),
                    OutboxEvent.attempts < MAX_ATTEMPTS,
                    or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
                )
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
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
                    follow_redirects=False,
                )
                # Redirects are not delivery acknowledgements: HTTPX does not
                # raise_for_status() on every 3xx response in all versions.
                # Never follow redirects with the internal bearer credential.
                if not 200 <= response.status_code < 300:
                    raise httpx.HTTPStatusError(
                        f"Receiver did not acknowledge delivery (HTTP {response.status_code})",
                        request=response.request,
                        response=response,
                    )
                event.published_at = datetime.now(timezone.utc)
                event.next_attempt_at = None
                event.last_error = None
            except (httpx.HTTPError, ValueError) as exc:
                # Redirects and permanent client errors cannot be recovered by
                # replaying the same payload. Preserve the row for inspection.
                # 408, 425 and 429 remain transient and honor the retry budget.
                permanent_rejection = permanent_receiver_rejection(exc)
                event.attempts = MAX_ATTEMPTS if permanent_rejection else event.attempts + 1
                # Once the retry budget is exhausted, keep the event for
                # operator inspection without advertising a future retry.
                event.next_attempt_at = (
                    datetime.now(timezone.utc) + receiver_retry_delay(exc, event.attempts)
                    if event.attempts < MAX_ATTEMPTS else None
                )
                event.last_error = (redact_text(str(exc)) or "")[:1000]
                log.warning("Outbox delivery failed for %s (attempt %s)", event.id, event.attempts)
            return True



def valid_webhook_endpoint(endpoint: str) -> bool:
    """Require an HTTPS host without URL-embedded credentials or query secrets."""
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > 2048 or endpoint != endpoint.strip():
        return False
    # URL parsers may normalize Unicode, whitespace, controls or backslashes.
    # Reject ambiguous raw destinations before handing them to HTTPX.
    if any(not 0x21 <= ord(char) <= 0x7E or char == "\\" for char in endpoint):
        return False
    # Reject even empty userinfo (https://@host), which HTTPX can expose
    # as empty username/password and otherwise silently accept.
    # Only the exact lowercase https:// prefix is accepted: a parser may
    # normalize mixed-case schemes or a missing authority delimiter.
    if not endpoint.startswith("https://"):
        return False
    authority = endpoint[len("https://"):].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    # Even empty query/fragment delimiters are forbidden. HTTPX exposes
    # their parsed values as empty bytes and otherwise hides their presence.
    if "@" in authority or "?" in endpoint or "#" in endpoint:
        return False
    # The receiver route is static: reject all percent-encoding, including
    # double-encoded separators (%252f) that intermediaries may decode twice.
    if "%" in endpoint:
        return False
    try:
        url = httpx.URL(endpoint)
        port = url.port
        # Internal receivers must use an explicit DNS name. Reject literal IPs
        # (including loopback, link-local and cloud metadata addresses) and
        # localhost aliases to avoid accidental credential delivery to them.
        host = url.host or ""
        try:
            ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            pass
        else:
            return False
        # A trailing root dot is valid DNS but changes URL/TLS hostname
        # canonicalization across clients. Require one unambiguous spelling.
        if host.endswith("."):
            return False
        normalized_host = host.lower()
        # Require canonical DNS labels: reject empty labels, underscores and
        # non-DNS characters rather than relying on resolver-specific parsing.
        if len(normalized_host) > 253 or not normalized_host or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in normalized_host.split(".")
        ):
            return False
        if normalized_host == "localhost" or normalized_host.endswith(".localhost"):
            return False
        # Numeric host aliases (decimal, octal-looking and hexadecimal,
        # including mixed dotted forms) may resolve to IPv4 even when
        # ipaddress rejects their non-canonical spelling.
        numeric_label = r"(?:[0-9]+|0[xX][0-9a-fA-F]+)"
        if re.fullmatch(rf"{numeric_label}(?:\.{numeric_label})*", normalized_host):
            return False
        return (
            (port is None or 1 <= port <= 65535)
            and url.scheme == "https"
            and bool(url.host)
            and not url.username
            and not url.password
            and not url.query
            and not url.fragment
        )
    except (httpx.InvalidURL, ValueError, TypeError):
        return False


async def main():
    endpoint = os.getenv("CORRELATION_WEBHOOK_URL", "")
    token = os.getenv("CORRELATION_WEBHOOK_TOKEN", "")
    allowed_host = os.getenv("CORRELATION_WEBHOOK_ALLOWED_HOST", "")
    if not valid_receiver_configuration(endpoint, token, allowed_host):
        raise RuntimeError(
            "Set HTTPS CORRELATION_WEBHOOK_URL, CORRELATION_WEBHOOK_TOKEN "
            "and exact CORRELATION_WEBHOOK_ALLOWED_HOST"
        )
    # Never inherit HTTP(S)_PROXY or NETRC from the worker environment:
    # the relay carries an internal bearer credential to a fixed receiver.
    # Bound the connection pool: this single-worker relay needs at most one
    # concurrent delivery and must not accumulate idle outbound sockets.
    async with httpx.AsyncClient(
        trust_env=False,
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
    ) as client:
        while True:
            worked = await dispatch_once(client, endpoint, token)
            if not worked:
                await asyncio.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
