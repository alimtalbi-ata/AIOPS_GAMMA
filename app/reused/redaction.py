"""Minimal fail-closed secret redaction for Gamma diagnostics.

Adapted from the threat model and specific GitHub/JWT token patterns in
Arvo-AI/aurora server/utils/auth/log_redact.py (Apache-2.0).
Unlike Aurora's broader tool output scanner, this helper rejects oversized
strings and avoids returning raw contents on a scanner exception.
"""
import re

MAX_TEXT = 100_000
_SECRET = "[REDACTED]"
PATTERNS = (
    re.compile(r"gh[sopru]_[A-Za-z0-9_]{8,}"),
    re.compile(r"eyJ[A-Za-z0-9_=-]+(?:\.[A-Za-z0-9_=-]+){1,2}"),
    re.compile(r"(?i)\b((?:Bearer|Basic)\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"""(?i)(\b(?:api[_-]?key|(?:client[_-]?)?secret|(?:db[_-]?)?password|(?:access|refresh)[_-]?token)\b["']?\s*[:=]\s*["']?)[^\s,;"'}]+"""),
)


def redact_text(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) > MAX_TEXT:
        return "[REDACTED:OVERSIZE]"
    try:
        for pattern in PATTERNS:
            value = pattern.sub(
                lambda match: (match.group(1) + _SECRET) if match.lastindex else _SECRET,
                value,
            )
        return value
    except Exception:
        return "[REDACTED:ERROR]"
