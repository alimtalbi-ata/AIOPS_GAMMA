"""Unit tests for signed, request-bound gateway principal assertions."""
import base64
import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException

from app.security import verify_gateway_assertion
from app.settings import settings


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _token(monkeypatch, **overrides):
    monkeypatch.setattr(settings, "gateway_assertion_secret", "s" * 48)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "trusted-gateway")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-api")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)
    claims = {
        "iss": "trusted-gateway", "aud": "gamma-api", "sub": "user:123",
        "actor_type": "user",
        "tenant_id": "12345678-1234-4234-8234-123456789abc",
        "tenant_access": True, "iat": 1000, "exp": 1060,
        "jti": "assertion-123456", "method": "POST",
        "path": "/api/v1/observability/metrics/query",
    }
    claims.update(overrides)
    encoded = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(b"s" * 48, encoded.encode("ascii"), hashlib.sha256).digest()
    return encoded + "." + _b64(signature)


def test_valid_assertion_returns_signed_actor_and_tenant(monkeypatch):
    principal = verify_gateway_assertion(_token(monkeypatch), method="POST",
        path="/api/v1/observability/metrics/query", now=1030)
    assert principal.subject == "user:123"
    assert principal.actor_type == "user"
    assert str(principal.tenant_id) == "12345678-1234-4234-8234-123456789abc"
    assert principal.assertion_id == "assertion-123456"


@pytest.mark.parametrize("method,path", [("GET", "/api/v1/observability/metrics/query"),
                                         ("POST", "/api/v1/other")])
def test_assertion_cannot_be_replayed_to_another_route(monkeypatch, method, path):
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(_token(monkeypatch), method=method, path=path, now=1030)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("claim,value", [("iss", "attacker"), ("aud", "other-api"),
    ("tenant_access", False), ("actor_type", "superadmin"),
    ("tenant_id", "00000000-0000-0000-0000-000000000000"), ("exp", 999), ("exp", 1200)])
def test_invalid_or_untrusted_claims_are_rejected(monkeypatch, claim, value):
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(_token(monkeypatch, **{claim: value}), method="POST",
            path="/api/v1/observability/metrics/query", now=1030)
    assert exc.value.status_code == 401


def test_tampered_signature_is_rejected(monkeypatch):
    encoded, _ = _token(monkeypatch).split(".")
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(encoded + "." + _b64(b"0" * 32), method="POST",
            path="/api/v1/observability/metrics/query", now=1030)
    assert exc.value.status_code == 401


def test_missing_verification_secret_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "gateway_assertion_secret", "")
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion("anything", method="POST",
            path="/api/v1/observability/metrics/query", now=1030)
    assert exc.value.status_code == 503



@pytest.mark.parametrize("token", ["abc.!!!", "x" * 9000, "not-a-token"])
def test_malformed_or_oversized_assertion_is_denied(monkeypatch, token):
    monkeypatch.setattr(settings, "gateway_assertion_secret", "s" * 48)
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            token, method="POST",
            path="/api/v1/observability/metrics/query", now=1030
        )
    assert exc.value.status_code == 401
