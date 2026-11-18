"""Synthetic review envelope. A digest is not a signature or authorization."""
import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4


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
    body = envelope["body"]
    digest = _digest(body)
    if not isinstance(expected_digest, str) or not hmac.compare_digest(digest, expected_digest) or not hmac.compare_digest(digest, envelope["sha256"]):
        raise ValueError("Digest mismatch")
    issued = _utc(datetime.fromisoformat(body["issued_at"]))
    expires = _utc(datetime.fromisoformat(body["expires_at"]))
    if not issued <= now < expires or not 0 < (expires-issued).total_seconds() <= 900:
        raise ValueError("Review outside validity window")
    return {"state": "SYNTHETIC_INTEGRITY_CHECKED", "id": body["id"],
            "approval_state": "NOT_GRANTED", "live_execution_authorized": False}
