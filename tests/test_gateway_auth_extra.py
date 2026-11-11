"""Extra fail-closed signed Gateway assertion checks (no live gateway)."""
import base64
import hashlib
import hmac
import json

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
