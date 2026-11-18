"""Synthetic review envelope. A digest is not a signature or authorization."""
import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4


def _utc(value):
    if type(value) is not datetime or value.utcoffset() is None:
        raise ValueError("Aware timestamp required")
    return value.astimezone(timezone.utc)


def _digest(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def seal_review(report, now, ttl_seconds=300):
    now = _utc(now)
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900:
        raise ValueError("Invalid TTL")
    if (type(report) is not dict or report.get("authoritative") is not False
            or report.get("live_execution_authorized") is not False
            or report.get("approval_state") != "NOT_GRANTED"):
        raise ValueError("Only unapproved synthetic reports accepted")
    body = {"id": str(uuid4()), "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
            "report": json.loads(json.dumps(report, allow_nan=False))}
    return {"body": body, "sha256": _digest(body)}


def check_review(envelope, now, expected_digest):
    now = _utc(now)
    if type(envelope) is not dict or set(envelope) != {"body", "sha256"}:
        raise ValueError("Invalid envelope")
    body = envelope["body"]
    if type(body) is not dict or set(body) != {"id", "issued_at", "expires_at", "report"}:
        raise ValueError("Invalid envelope body")
    if type(body["id"]) is not str or str(UUID(body["id"])) != body["id"] or UUID(body["id"]).version != 4:
        raise ValueError("Invalid dossier identity")
    report = body["report"]
    if (type(report) is not dict or report.get("authoritative") is not False
            or report.get("live_execution_authorized") is not False
            or report.get("approval_state") != "NOT_GRANTED"):
        raise ValueError("Only unapproved synthetic reports accepted")
    if any(type(body[k]) is not str for k in ("issued_at", "expires_at")):
        raise ValueError("Invalid timestamps")
    if any(type(v) is not str or len(v) != 64 or any(ch not in "0123456789abcdef" for ch in v)
           for v in (expected_digest, envelope["sha256"])):
        raise ValueError("Digest mismatch")
    digest = _digest(body)
    if not isinstance(expected_digest, str) or not hmac.compare_digest(digest, expected_digest) or not hmac.compare_digest(digest, envelope["sha256"]):
        raise ValueError("Digest mismatch")
    issued = _utc(datetime.fromisoformat(body["issued_at"]))
    expires = _utc(datetime.fromisoformat(body["expires_at"]))
    if not issued <= now < expires or not 0 < (expires-issued).total_seconds() <= 900:
        raise ValueError("Review outside validity window")
    return {"state": "SYNTHETIC_INTEGRITY_CHECKED", "id": body["id"],
            "approval_state": "NOT_GRANTED", "live_execution_authorized": False}
