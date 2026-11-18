"""At-least-once outbox relay.

One transaction per delivery attempt. The row is locked during the HTTP call,
so only deploy against a trusted low-latency internal receiver. The receiver
MUST deduplicate by X-Event-Id. No external endpoint is configured by default.
"""
import asyncio
import ipaddress
import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

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
    return timedelta(seconds=min(300, 2 ** min(attempts, 9)))


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
    """Bound numeric or HTTP-date Retry-After for 425/429/503 to 300 seconds."""
    default = retry_delay(attempts)
    if not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code not in (425, 429, 503):
        return default
    # Multiple Retry-After fields are ambiguous. Do not let a combined
    # header override our bounded local backoff.
    values = exc.response.headers.get_list("retry-after")
    if len(values) != 1:
        return default
    value = values[0]
    if not value or len(value) > 128 or not value.isascii():
        return default
    if value.isdecimal():
        if len(value) > 6:
            return default
        seconds = int(value)
    else:
        # Retry-After HTTP-date is an IMF-fixdate in GMT. Reject permissive
        # email-date variants (including local timezones) rather than
        # accepting ambiguous or non-standard scheduling instructions.
        if not re.fullmatch(
            r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), "
            r"[0-9]{2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
            r"[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2} GMT",
            value,
        ):
            return default
        try:
            deadline = parsedate_to_datetime(value)
            current = now or datetime.now(timezone.utc)
            if (
                deadline.tzinfo is None
                or current.tzinfo is None
                or current.utcoffset() is None
                or deadline.strftime("%a, %d %b %Y %H:%M:%S GMT") != value
            ):
                return default
            seconds = (deadline - current.astimezone(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return default
    return timedelta(seconds=max(default.total_seconds(), min(seconds, 300)))


async def dispatch_once(client: httpx.AsyncClient, endpoint: str, token: str) -> bool:
    raise RuntimeError("Outbox dispatch disabled pending tenant-aware RLS qualification")


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
    # No qualified tenant-aware worker identity exists yet.
    raise RuntimeError("Outbox relay disabled pending tenant-aware RLS qualification")


async def _unqualified_relay_main():
    raise RuntimeError("Unqualified relay disabled")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
