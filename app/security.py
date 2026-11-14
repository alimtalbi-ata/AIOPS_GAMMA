"""Fail-closed gateway assertion verification for tenant-scoped API access.

The gateway MUST authenticate the actor, check actor→tenant membership, strip
untrusted identity headers, then sign a short-lived, request-bound assertion.
The service API key is a separate service-to-service credential, not a tenant
authorization decision. Network policy/mTLS must prevent gateway bypass.
"""
import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException, Request

from app.settings import settings


@dataclass(frozen=True)
class Principal:
    tenant_id: UUID
    subject: str
    actor_type: str
    assertion_id: str
    expires_at: int


def _b64url_decode(value: str) -> bytes:
    if not value or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for ch in value):
        raise ValueError("invalid base64url")
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
        raise ValueError("noncanonical base64url")
    return decoded


def _unique_claims(pairs: list[tuple[str, object]]) -> dict[str, object]:
    claims = {}
    for key, value in pairs:
        if key in claims:
            raise ValueError("duplicate assertion claim")
        claims[key] = value
    return claims


def verify_gateway_assertion(token: str, *, method: str, path: str, now: int | None = None) -> Principal:
    if not isinstance(token, str) or len(token) > 8192:
        raise HTTPException(status_code=401, detail="Invalid gateway principal assertion")
    secret = settings.gateway_assertion_secret
    if not secret or len(secret.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail="Gateway assertion verification not configured")
    if not settings.gateway_assertion_issuer or not settings.gateway_assertion_audience:
        raise HTTPException(status_code=503, detail="Gateway assertion policy not configured")
    # A misconfigured deployment must never relax the 60-second security ceiling.
    max_ttl = settings.gateway_assertion_max_ttl_seconds
    if type(max_ttl) is not int or not 1 <= max_ttl <= 60:
        raise HTTPException(status_code=503, detail="Gateway assertion TTL policy invalid")
    try:
        encoded, signature = token.split(".")
        supplied_signature = _b64url_decode(signature)
        expected_signature = hmac.new(
            secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("signature mismatch")
        claims = json.loads(
            _b64url_decode(encoded), object_pairs_hook=_unique_claims,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON constant")),
        )
        if not isinstance(claims, dict):
            raise ValueError("claims must be an object")
        current = int(time.time()) if now is None else now
        issued_at, expires_at = claims.get("iat"), claims.get("exp")
        if (isinstance(issued_at, bool) or not isinstance(issued_at, int)
                or isinstance(expires_at, bool) or not isinstance(expires_at, int)):
            raise ValueError("invalid assertion timestamps")
        if issued_at > current + 5 or expires_at <= current:
            raise ValueError("assertion not currently valid")
        if expires_at <= issued_at or expires_at - issued_at > settings.gateway_assertion_max_ttl_seconds:
            raise ValueError("assertion lifetime exceeds policy")
        if claims.get("iss") != settings.gateway_assertion_issuer:
            raise ValueError("invalid issuer")
        if claims.get("aud") != settings.gateway_assertion_audience:
            raise ValueError("invalid audience")
        if claims.get("method") != method or claims.get("path") != path:
            raise ValueError("assertion is not bound to this request")
        subject = claims.get("sub")
        actor_type = claims.get("actor_type")
        assertion_id = claims.get("jti")
        if (not isinstance(subject, str) or not subject.strip() or len(subject) > 256
                or any(ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF for ch in subject)):
            raise ValueError("invalid subject")
        if actor_type not in ("user", "service"):
            raise ValueError("invalid actor type")
        if (not isinstance(assertion_id, str) or not 8 <= len(assertion_id) <= 128
                or not assertion_id.isascii() or any(not (33 <= ord(ch) <= 126) for ch in assertion_id)):
            raise ValueError("invalid assertion id")
        if claims.get("tenant_access") is not True:
            raise ValueError("tenant membership not attested")
        tenant_raw = claims.get("tenant_id")
        tenant = UUID(tenant_raw if isinstance(tenant_raw, str) else "")
        if tenant.int == 0 or tenant_raw != str(tenant):
            raise ValueError("invalid tenant")
        return Principal(tenant_id=tenant, subject=subject, actor_type=actor_type,
                         assertion_id=assertion_id, expires_at=expires_at)
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid gateway principal assertion") from exc


def internal_principal(
    request: Request,
    x_internal_api_key: str | None = Header(default=None),
    x_gateway_principal: str | None = Header(default=None),
) -> Principal:
    # The service key authenticates the calling workload only. It does NOT
    # authorize a tenant and cannot be used with a caller-selected X-Tenant-ID.
    if not settings.internal_api_key:
        raise HTTPException(status_code=503, detail="Internal service authentication not configured")
    try:
        supplied_key = x_internal_api_key.encode("utf-8") if x_internal_api_key else b""
        expected_key = settings.internal_api_key.encode("utf-8")
    except UnicodeError as exc:
        raise HTTPException(status_code=401, detail="Unauthorized") from exc
    if not supplied_key or not hmac.compare_digest(supplied_key, expected_key):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not x_gateway_principal:
        raise HTTPException(status_code=401, detail="Verified gateway principal required")
    return verify_gateway_assertion(
        x_gateway_principal, method=request.method, path=request.url.path
    )
