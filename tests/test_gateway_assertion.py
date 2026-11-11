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
    assert principal.expires_at == 1060


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


def test_duplicate_signed_claim_is_rejected(monkeypatch):
    _token(monkeypatch)
    payload = (
        '{"iss":"trusted-gateway","iss":"trusted-gateway",'
        '"aud":"gamma-api","sub":"user:123","actor_type":"user",'
        '"tenant_id":"12345678-1234-4234-8234-123456789abc",'
        '"tenant_access":true,"iat":1000,"exp":1060,'
        '"jti":"assertion-123456","method":"POST",'
        '"path":"/api/v1/observability/metrics/query"}'
    )
    encoded = _b64(payload.encode())
    signature = hmac.new(b"s" * 48, encoded.encode(), hashlib.sha256).digest()
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(encoded + "." + _b64(signature),
            method="POST", path="/api/v1/observability/metrics/query", now=1030)
    assert exc.value.status_code == 401


def test_noncanonical_base64url_signature_is_rejected(monkeypatch):
    token = _token(monkeypatch)
    encoded, signature = token.split(".")
    # Padding is not part of the canonical unpadded base64url wire format.
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(encoded + "." + signature + "=",
            method="POST", path="/api/v1/observability/metrics/query", now=1030)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("claim,value", [
    ("iat", 1036),  # more than five seconds into the future
    ("iat", True),  # bool is an int subclass but not a valid timestamp
    ("exp", True),
    ("exp", 1000),  # expires at issuance
    ("exp", 1061),  # 61-second lifetime exceeds configured maximum
])
def test_invalid_signed_timestamp_boundaries_denied(monkeypatch, claim, value):
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            _token(monkeypatch, **{claim: value}),
            method="POST", path="/api/v1/observability/metrics/query", now=1030,
        )
    assert exc.value.status_code == 401


def test_exact_expiry_boundary_is_denied(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            _token(monkeypatch), method="POST",
            path="/api/v1/observability/metrics/query", now=1060,
        )
    assert exc.value.status_code == 401


@pytest.mark.parametrize("configured_ttl", [0, -1, 61, 3600, True, False, 30.5])
def test_invalid_gateway_ttl_configuration_fails_closed(monkeypatch, configured_ttl):
    token = _token(monkeypatch)
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", configured_ttl)
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            token, method="POST",
            path="/api/v1/observability/metrics/query", now=1030,
        )
    assert exc.value.status_code == 503


def test_stricter_gateway_ttl_configuration_is_enforced(monkeypatch):
    token = _token(monkeypatch)
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 30)
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            token, method="POST",
            path="/api/v1/observability/metrics/query", now=1030,
        )
    assert exc.value.status_code == 401


@pytest.mark.parametrize("claim,value", [
    ("sub", ""), ("sub", "   "), ("sub", "x" * 257),
    ("jti", ""), ("jti", "short"), ("jti", "x" * 129),
    ("jti", None), ("sub", None),
    ("jti", "        "), ("jti", "abc\\n12345"),
    ("jti", "é" * 8),
])
def test_invalid_signed_actor_identity_fields_denied(monkeypatch, claim, value):
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            _token(monkeypatch, **{claim: value}), method="POST",
            path="/api/v1/observability/metrics/query", now=1030,
        )
    assert exc.value.status_code == 401


def test_unicode_service_key_header_denied_without_uncaught_type_error(monkeypatch):
    from starlette.requests import Request
    from app.security import internal_principal

    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    request = Request({"type": "http", "method": "POST", "path": "/probe",
                       "headers": [], "query_string": b""})
    with pytest.raises(HTTPException) as exc:
        internal_principal(
            request, x_internal_api_key="clé-invalide",
            x_gateway_principal="not-a-valid-assertion",
        )
    assert exc.value.status_code == 401


@pytest.mark.parametrize("subject", [
    "user\\nadmin", "user\\radmin", "user\\tadmin",
    "user\\x00admin", "user\\x7fadmin",
])
def test_control_characters_in_signed_subject_denied(monkeypatch, subject):
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            _token(monkeypatch, sub=subject), method="POST",
            path="/api/v1/observability/metrics/query", now=1030,
        )
    assert exc.value.status_code == 401
