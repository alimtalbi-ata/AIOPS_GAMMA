"""Extra fail-closed signed Gateway assertion checks (no live gateway)."""
import base64
import hashlib
import hmac
import json

from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import HTTPException
from app.security import verify_gateway_assertion
from app.settings import settings


def signed(monkeypatch, **changes):
    monkeypatch.setattr(settings, 'gateway_assertion_secret', 's' * 48)
    monkeypatch.setattr(settings, 'gateway_assertion_issuer', 'trusted-gateway')
    monkeypatch.setattr(settings, 'gateway_assertion_audience', 'gamma-api')
    monkeypatch.setattr(settings, 'gateway_assertion_max_ttl_seconds', 60)
    claims = {'iss':'trusted-gateway', 'aud':'gamma-api', 'sub':'user:123',
              'actor_type':'user', 'tenant_id':'12345678-1234-4234-8234-123456789abc',
              'tenant_access':True, 'iat':1000, 'exp':1060, 'jti':'assertion-123456',
              'method':'POST', 'path':'/api/v1/observability/metrics/query'}
    claims.update(changes)
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b'=').decode()
    sig = base64.urlsafe_b64encode(hmac.new(b's'*48, payload.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
    return payload+'.'+sig


@pytest.mark.parametrize('claim,value', [
    ('sub', 'user\nadmin'), ('sub','user\radmin'), ('sub','user\tadmin'),
    ('sub','user\x00admin'), ('sub','user\x7fadmin'),
    ('jti','abc\n12345'), ('jti','é'*8), ('jti','short'),
    ('tenant_id','12345678-1234-4234-8234-123456789ABC'),
    ('tenant_access',1), ('iat',True), ('exp',True),
])
def test_signed_invalid_claim_rejected(monkeypatch, claim, value):
    token=signed(monkeypatch, **{claim:value})
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(token, method='POST',path='/api/v1/observability/metrics/query',now=1030)
    assert exc.value.status_code==401


def test_service_actor_with_valid_tenant_attestation(monkeypatch):
    token=signed(monkeypatch,actor_type='service',sub='service:collector')
    principal=verify_gateway_assertion(token,method='POST',path='/api/v1/observability/metrics/query',now=1030)
    assert principal.actor_type=='service'
    assert principal.subject=='service:collector'

@pytest.mark.parametrize('fragment', ['NaN', 'Infinity', '-Infinity'])
def test_nonfinite_nested_signed_claim_rejected(monkeypatch, fragment):
    token = signed(monkeypatch)
    encoded, _ = token.split('.')
    raw = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode()
    raw = raw[:-1] + ',"nested":{"value":' + fragment + '}}'
    encoded = base64.urlsafe_b64encode(raw.encode()).rstrip(b'=').decode()
    signature = base64.urlsafe_b64encode(
        hmac.new(b's' * 48, encoded.encode(), hashlib.sha256).digest()
    ).rstrip(b'=').decode()
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(encoded + '.' + signature, method='POST',
                                 path='/api/v1/observability/metrics/query', now=1030)
    assert exc.value.status_code == 401

@pytest.mark.parametrize('bad_subject', ['user:\ud800', 'user:\udfff'])
def test_signed_unpaired_surrogate_subject_rejected(monkeypatch, bad_subject):
    token = signed(monkeypatch, sub=bad_subject)
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(token, method='POST',
                                 path='/api/v1/observability/metrics/query', now=1030)
    assert exc.value.status_code == 401

@pytest.mark.parametrize("ttl", [1, 30, 60])
def test_assertion_ttl_within_configured_security_ceiling_is_accepted(monkeypatch, ttl):
    token = signed(monkeypatch, iat=1000, exp=1000 + ttl)
    principal = verify_gateway_assertion(
        token, method="POST",
        path="/api/v1/observability/metrics/query",
        now=1000,
    )
    assert principal.expires_at == 1000 + ttl


@pytest.mark.parametrize("invalid_ttl", [0, -1, 61, True, 1.5])
def test_invalid_configured_assertion_ttl_fails_closed(monkeypatch, invalid_ttl):
    token = signed(monkeypatch, iat=1000, exp=1030)
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", invalid_ttl)
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            token, method="POST",
            path="/api/v1/observability/metrics/query",
            now=1010,
        )
    assert exc.value.status_code == 503


@pytest.mark.parametrize("missing_policy", ["issuer", "audience"])
def test_missing_gateway_policy_fails_closed(monkeypatch, missing_policy):
    token = signed(monkeypatch)
    attribute = (
        "gateway_assertion_issuer"
        if missing_policy == "issuer"
        else "gateway_assertion_audience"
    )
    monkeypatch.setattr(settings, attribute, "")
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            token, method="POST",
            path="/api/v1/observability/metrics/query",
            now=1030,
        )
    assert exc.value.status_code == 503


def test_weak_gateway_secret_fails_closed(monkeypatch):
    token = signed(monkeypatch)
    monkeypatch.setattr(settings, "gateway_assertion_secret", "x" * 31)
    with pytest.raises(HTTPException) as exc:
        verify_gateway_assertion(
            token, method="POST",
            path="/api/v1/observability/metrics/query",
            now=1030,
        )
    assert exc.value.status_code == 503

from starlette.requests import Request
from app.security import internal_principal


def request_with_headers(path="/api/v1/observability/metrics/query", headers=None, method="POST"):
    raw_headers = [(key.lower().encode("latin-1"), value.encode("latin-1"))
                   for key, value in (headers or {}).items()]
    return Request({
        "type": "http", "asgi": {"version": "3.0"},
        "http_version": "1.1", "method": method, "scheme": "http",
        "path": path, "raw_path": path.encode(), "query_string": b"",
        "headers": raw_headers, "server": ("testserver", 80),
        "client": ("testclient", 12345),
    })


@pytest.mark.parametrize("supplied_key", [None, "", "wrong-service-key"])
@pytest.mark.asyncio
async def test_internal_principal_rejects_missing_or_wrong_service_key(monkeypatch, supplied_key):
    monkeypatch.setattr(settings, "internal_api_key", "service-secret")
    request = request_with_headers()
    with pytest.raises(HTTPException) as exc:
        await internal_principal(request, x_internal_api_key=supplied_key,
                           x_gateway_principal=signed(monkeypatch))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_internal_principal_fails_closed_when_service_key_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "")
    with pytest.raises(HTTPException) as exc:
        await internal_principal(request_with_headers(), x_internal_api_key="anything",
                           x_gateway_principal=None)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_internal_principal_requires_gateway_assertion_after_service_auth(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "service-secret")
    with pytest.raises(HTTPException) as exc:
        await internal_principal(request_with_headers(), x_internal_api_key="service-secret",
                           x_gateway_principal=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_internal_principal_ignores_caller_selected_tenant_header(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "service-secret")
    monkeypatch.setattr("app.security.time.time", lambda: 1030)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=object())
    context.__aexit__ = AsyncMock(return_value=False)
    consume = AsyncMock(return_value=True)
    monkeypatch.setattr("app.security.get_session_factory", lambda: lambda: context)
    monkeypatch.setattr("app.security.consume_assertion_before_access", consume)
    token = signed(monkeypatch)
    request = request_with_headers(headers={"X-Tenant-ID": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"})
    principal = await internal_principal(
        request, x_internal_api_key="service-secret", x_gateway_principal=token
    )
    assert str(principal.tenant_id) == "12345678-1234-4234-8234-123456789abc"
    consume.assert_awaited_once()


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/observability/metrics/query"),
    ("POST", "/api/v1/observability/logs/search"),
])
@pytest.mark.asyncio
async def test_internal_principal_rejects_assertion_bound_to_other_request(monkeypatch, method, path):
    monkeypatch.setattr(settings, "internal_api_key", "service-secret")
    monkeypatch.setattr("app.security.time.time", lambda: 1030)
    token = signed(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await internal_principal(
            request_with_headers(path=path, method=method),
            x_internal_api_key="service-secret", x_gateway_principal=token,
        )
    assert exc.value.status_code == 401
