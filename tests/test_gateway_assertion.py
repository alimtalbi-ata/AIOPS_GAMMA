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
    ("sub", ""), ("sub", "   "), ("sub", " user:123"), ("sub", "user:123 "), ("sub", "x" * 257),
    ("jti", ""), ("jti", "short"), ("jti", "x" * 129),
    ("jti", None), ("sub", None),
    ("jti", "        "), ("jti", "abc\n12345"),
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
    "user\nadmin", "user\radmin", "user\tadmin",
    "user\x00admin", "user\x7fadmin",
])
def test_control_characters_in_signed_subject_denied(monkeypatch, subject):
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            _token(monkeypatch, sub=subject), method="POST",
            path="/api/v1/observability/metrics/query", now=1030,
        )
    assert exc.value.status_code == 401


@pytest.mark.parametrize("nonfinite", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_constant_in_signed_claims_denied(monkeypatch, nonfinite):
    # Even a valid HMAC must not make non-standard JSON constants acceptable.
    token = _token(monkeypatch)
    encoded, _ = token.split(".")
    payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    payload = payload[:-1] + ',"untrusted_extra":' + nonfinite + '}'
    encoded = _b64(payload.encode())
    signature = hmac.new(b"s" * 48, encoded.encode("ascii"), hashlib.sha256).digest()
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            encoded + "." + _b64(signature), method="POST",
            path="/api/v1/observability/metrics/query", now=1030,
        )
    assert exc.value.status_code == 401


@pytest.mark.parametrize("malformed_key", ["\ud800", "prefix\udfff", "\ud800\udfff"])
def test_malformed_unicode_service_key_header_fails_closed(monkeypatch, malformed_key):
    from starlette.requests import Request
    from app.security import internal_principal

    monkeypatch.setattr(settings, "internal_api_key", "lab-secret")
    request = Request({"type": "http", "method": "POST", "path": "/probe",
                       "headers": [], "query_string": b""})
    with pytest.raises(HTTPException) as exc:
        internal_principal(request, x_internal_api_key=malformed_key,
                           x_gateway_principal="not-a-valid-assertion")
    assert exc.value.status_code == 401


@pytest.mark.parametrize("configured_secret", ["\ud800" + "s" * 48, "\udfff", None])
def test_malformed_gateway_verifier_secret_fails_closed_as_configuration_error(monkeypatch, configured_secret):
    token = _token(monkeypatch)
    monkeypatch.setattr(settings, "gateway_assertion_secret", configured_secret)
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(token, method="POST",
            path="/api/v1/observability/metrics/query", now=1030)
    assert exc.value.status_code == 503


@pytest.mark.parametrize("subject", [
    "user\u200b:123",  # zero-width space
    "user\u202e:123",  # right-to-left override
    "user\u2066:123",  # left-to-right isolate
])
def test_invisible_unicode_format_controls_in_signed_subject_denied(monkeypatch, subject):
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            _token(monkeypatch, sub=subject),
            method="POST", path="/api/v1/observability/metrics/query", now=1030,
        )
    assert exc.value.status_code == 401


def test_signed_service_grants_default_to_deny(monkeypatch):
    principal = verify_gateway_assertion(_token(monkeypatch), method="POST",
        path="/api/v1/observability/metrics/query", now=1030)
    assert principal.log_service_grants == ()


def test_signed_service_grants_preserved_as_exact_names(monkeypatch):
    token = _token(monkeypatch, log_service_grants=["checkout", "billing-api"])
    principal = verify_gateway_assertion(token, method="POST",
        path="/api/v1/observability/metrics/query", now=1030)
    assert principal.log_service_grants == ("checkout", "billing-api")


@pytest.mark.parametrize("grants", [
    "*", ["*"], ["checkout", "checkout"], [" checkout"], [""],
    ["checkout", 12], [None], ["x" * 256], list(range(33)),
])
def test_malformed_signed_service_grants_fail_closed(monkeypatch, grants):
    token = _token(monkeypatch, log_service_grants=grants)
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(token, method="POST",
            path="/api/v1/observability/metrics/query", now=1030)
    assert exc.value.status_code == 401


def test_evidence_incident_grants_default_deny(monkeypatch):
    principal = verify_gateway_assertion(_token(monkeypatch), method="POST",
        path="/api/v1/observability/metrics/query", now=1030)
    assert principal.evidence_incident_grants == ()


def test_evidence_incident_grants_preserve_exact_resource_ids(monkeypatch):
    token = _token(monkeypatch, evidence_incident_grants=["inc-1", "inc-2"])
    principal = verify_gateway_assertion(token, method="POST",
        path="/api/v1/observability/metrics/query", now=1030)
    assert principal.evidence_incident_grants == ("inc-1", "inc-2")


@pytest.mark.parametrize("grants", [
    "*", ["inc-1", "inc-1"], [" inc-1"], [""], [123],
    [None], ["x" * 256], list(range(65)), ["inc-1\\nspoof"],
    ["inc-1\u200b"], ["inc-1\u202e"],
])
def test_malformed_evidence_incident_grants_fail_closed(monkeypatch, grants):
    token = _token(monkeypatch, evidence_incident_grants=grants)
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(token, method="POST",
            path="/api/v1/observability/metrics/query", now=1030)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("resource", ["inc/1", "inc?1", "inc#1"])
def test_signed_incident_grants_reject_url_delimiters(monkeypatch, resource):
    token = _token(monkeypatch, evidence_incident_grants=[resource])
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(token, method="POST",
            path="/api/v1/observability/metrics/query", now=1030)
    assert exc.value.status_code == 401


def test_signed_incident_grants_reject_non_nfc_alias(monkeypatch):
    token = _token(monkeypatch, evidence_incident_grants=["cafe\u0301"])
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(token, method="POST",
            path="/api/v1/observability/metrics/query", now=1030)
    assert exc.value.status_code == 401


def test_signed_incident_grants_accept_nfc_resource(monkeypatch):
    token = _token(monkeypatch, evidence_incident_grants=["caf\u00e9"])
    principal = verify_gateway_assertion(token, method="POST",
        path="/api/v1/observability/metrics/query", now=1030)
    assert principal.evidence_incident_grants == ("caf\u00e9",)


@pytest.mark.parametrize("resource", ["inc\u0085name", "inc\u009fname"])
def test_signed_incident_grants_reject_c1_controls(monkeypatch, resource):
    token = _token(monkeypatch, evidence_incident_grants=[resource])
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(token, method="POST",
            path="/api/v1/observability/metrics/query", now=1030)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_internal_principal_consumes_jti_before_access(monkeypatch):
    from starlette.requests import Request
    import app.security as security

    monkeypatch.setattr(settings, "internal_api_key", "service-key")
    monkeypatch.setattr(security.time, "time", lambda: 1030)
    token = _token(monkeypatch)
    calls = []
    session = object()
    monkeypatch.setattr(security, "get_session_factory", lambda: lambda: _ReplaySessionContext(session))

    async def consume(session, *, issuer, assertion_id, expires_at):
        calls.append((session, issuer, assertion_id, expires_at))
        return True

    monkeypatch.setattr(security, "consume_assertion_before_access", consume)
    scope = {
        "type": "http", "method": "POST",
        "path": "/api/v1/observability/metrics/query",
        "headers": [
            (b"x-internal-api-key", b"service-key"),
            (b"x-gateway-principal", token.encode()),
        ],
        "query_string": b"", "server": ("test", 80),
        "client": ("127.0.0.1", 1234), "scheme": "http",
    }
    principal = await security.internal_principal(
        Request(scope), "service-key", token
    )
    assert principal.assertion_id == "assertion-123456"
    assert calls == [(session, "trusted-gateway", "assertion-123456", 1060)]


@pytest.mark.asyncio
async def test_internal_principal_rejects_replayed_jti(monkeypatch):
    from starlette.requests import Request
    import app.security as security

    monkeypatch.setattr(settings, "internal_api_key", "service-key")
    monkeypatch.setattr(security.time, "time", lambda: 1030)
    token = _token(monkeypatch)

    session = object()
    monkeypatch.setattr(security, "get_session_factory", lambda: lambda: _ReplaySessionContext(session))

    async def duplicate(*args, **kwargs):
        return False

    monkeypatch.setattr(security, "consume_assertion_before_access", duplicate)
    scope = {
        "type": "http", "method": "POST",
        "path": "/api/v1/observability/metrics/query",
        "headers": [
            (b"x-internal-api-key", b"service-key"),
            (b"x-gateway-principal", token.encode()),
        ],
        "query_string": b"", "server": ("test", 80),
        "client": ("127.0.0.1", 1234), "scheme": "http",
    }
    with pytest.raises(HTTPException) as exc:
        await security.internal_principal(Request(scope), "service-key", token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Gateway assertion already used"


@pytest.mark.asyncio
async def test_internal_principal_fails_closed_when_replay_store_unavailable(monkeypatch):
    from starlette.requests import Request
    import app.security as security

    monkeypatch.setattr(settings, "internal_api_key", "service-key")
    monkeypatch.setattr(security.time, "time", lambda: 1030)
    token = _token(monkeypatch)

    session = object()
    monkeypatch.setattr(security, "get_session_factory", lambda: lambda: _ReplaySessionContext(session))

    async def unavailable(*args, **kwargs):
        raise RuntimeError("database internals must not leak")

    monkeypatch.setattr(security, "consume_assertion_before_access", unavailable)
    scope = {
        "type": "http", "method": "POST",
        "path": "/api/v1/observability/metrics/query",
        "headers": [
            (b"x-internal-api-key", b"service-key"),
            (b"x-gateway-principal", token.encode()),
        ],
        "query_string": b"", "server": ("test", 80),
        "client": ("127.0.0.1", 1234), "scheme": "http",
    }
    with pytest.raises(HTTPException) as exc:
        await security.internal_principal(Request(scope), "service-key", token)
    assert exc.value.status_code == 503
    assert exc.value.detail == "Gateway replay protection unavailable"


class _ReplaySessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_resource_grants_are_scoped_and_default_to_no_access(monkeypatch):
    base = verify_gateway_assertion(
        _token(monkeypatch), method="POST",
        path="/api/v1/observability/metrics/query", now=1030,
    )
    assert base.log_service_grants == ()
    assert base.evidence_incident_grants == ()

    scoped = verify_gateway_assertion(
        _token(monkeypatch, log_service_grants=["checkout-api"],
               evidence_incident_grants=["INC-123"]),
        method="POST", path="/api/v1/observability/metrics/query", now=1030,
    )
    assert scoped.log_service_grants == ("checkout-api",)
    assert scoped.evidence_incident_grants == ("INC-123",)


@pytest.mark.parametrize("claim,value", [
    ("log_service_grants", ["checkout-api", "*"]),
    ("log_service_grants", ["checkout-api", "checkout-api"]),
    ("log_service_grants", ["bad/service"]),
    ("evidence_incident_grants", ["*"]),
    ("evidence_incident_grants", ["INC-1", "INC-1"]),
    ("evidence_incident_grants", ["../other-tenant"]),
    ("evidence_incident_grants", ["INC-1\\x00"]),
])
def test_malformed_or_overbroad_resource_grants_are_rejected(monkeypatch, claim, value):
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            _token(monkeypatch, **{claim: value}),
            method="POST", path="/api/v1/observability/metrics/query", now=1030,
        )
    assert exc.value.status_code == 401
