"""Offline HMAC simulation. Keys and actors are synthetic, never live credentials."""
import hashlib
import hmac
import json
from app.reused.shadow_review_integrity import check_review


def _mac(key, claims):
    if type(key) is not bytes or len(key) < 32:
        raise ValueError("Synthetic key must contain at least 32 bytes")
    return hmac.new(key, b"gamma-shadow-review-v1\x00" + json.dumps(
        claims, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode(), hashlib.sha256).hexdigest()


def sign_synthetic_review(envelope, now, expected_digest, actor, tenant, key_id, key):
    check_review(envelope, now, expected_digest)
    if any(type(v) is not str or not v.strip() for v in (actor, tenant, key_id)):
        raise ValueError("Missing identity")
    if envelope["body"]["report"].get("tenant_id") != tenant:
        raise ValueError("Tenant mismatch")
    claims = {"actor": actor, "tenant": tenant, "key_id": key_id, "digest": expected_digest}
    return {"claims": claims, "mac": _mac(key, claims)}


def verify_synthetic_review(envelope, now, attestation, actor, tenant, keys):
    claims = attestation["claims"]
    if set(claims) != {"actor", "tenant", "key_id", "digest"}:
        raise ValueError("Invalid claims")
    if claims["actor"] != actor or claims["tenant"] != tenant:
        raise ValueError("Identity mismatch")
    if claims["key_id"] not in keys:
        raise ValueError("Unknown or retired key")
    if not hmac.compare_digest(_mac(keys[claims["key_id"]], claims), attestation["mac"]):
        raise ValueError("MAC mismatch")
    check_review(envelope, now, claims["digest"])
    if envelope["body"]["report"].get("tenant_id") != tenant:
        raise ValueError("Tenant mismatch")
    return {"state": "SYNTHETIC_MAC_VERIFIED", "approval_state": "NOT_GRANTED",
            "authoritative": False, "live_execution_authorized": False}
