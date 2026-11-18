"""HTTP dependency boundary against exact GitHub security/settings modules; isolated FastAPI harness."""
import base64
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.security import Principal, internal_principal
from app.settings import settings

app = FastAPI()

@app.post('/api/v1/probe')
def probe(principal: Principal = Depends(internal_principal)):
    return {'subject': principal.subject, 'tenant': str(principal.tenant_id)}

@app.get('/api/v1/probe')
def get_probe(principal: Principal = Depends(internal_principal)):
    return {'subject': principal.subject}

@pytest.fixture(autouse=True)
def configure(monkeypatch):
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=object())
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr('app.security.get_session_factory', lambda: lambda: context)
    seen = set()

    async def reserve(session, *, issuer, assertion_id, expires_at):
        key = (issuer, assertion_id)
        if key in seen:
            return False
        seen.add(key)
        return True

    monkeypatch.setattr('app.security.consume_assertion_before_access', reserve)
    monkeypatch.setattr(settings, 'internal_api_key', 'service-secret')
    monkeypatch.setattr(settings, 'gateway_assertion_secret', 's'*48)
    monkeypatch.setattr(settings, 'gateway_assertion_issuer', 'trusted-gateway')
    monkeypatch.setattr(settings, 'gateway_assertion_audience', 'gamma-api')
    monkeypatch.setattr(settings, 'gateway_assertion_max_ttl_seconds', 60)

def signed(*, method='POST', path='/api/v1/probe', tenant_access=True, overrides=None):
    now = int(time.time())
    claims = {'iss':'trusted-gateway','aud':'gamma-api','sub':'user:123',
              'actor_type':'user','tenant_id':str(uuid4()),'tenant_access':tenant_access,
              'iat':now,'exp':now+30,'jti':'assertion-123456', 'method':method,'path':path}
    claims.update(overrides or {})
    return signed_json(json.dumps(claims, separators=(',', ':')))


def signed_json(raw_claims):
    encoded = base64.urlsafe_b64encode(raw_claims.encode()).rstrip(b'=').decode()
    signature = base64.urlsafe_b64encode(hmac.new(b's'*48,encoded.encode(),hashlib.sha256).digest()).rstrip(b'=').decode()
    return encoded+'.'+signature

def test_no_service_key_rejected():
    with TestClient(app) as client:
        r=client.post('/api/v1/probe',headers={'X-Gateway-Principal':signed()})
    assert r.status_code == 401

def test_key_alone_rejected_even_with_forged_tenant_and_actor():
    with TestClient(app) as client:
        r=client.post('/api/v1/probe',headers={'X-Internal-API-Key':'service-secret','X-Tenant-ID':str(uuid4()),'X-Actor-ID':'admin'})
    assert r.status_code == 401

def test_wrong_service_key_rejected():
    with TestClient(app) as client:
        r=client.post('/api/v1/probe',headers={'X-Internal-API-Key':'wrong','X-Gateway-Principal':signed()})
    assert r.status_code == 401

def test_signed_tenant_access_false_rejected():
    with TestClient(app) as client:
        r=client.post('/api/v1/probe',headers={'X-Internal-API-Key':'service-secret','X-Gateway-Principal':signed(tenant_access=False)})
    assert r.status_code == 401

def test_valid_signed_principal_accepted():
    with TestClient(app) as client:
        r=client.post('/api/v1/probe',headers={'X-Internal-API-Key':'service-secret','X-Gateway-Principal':signed()})
    assert r.status_code == 200 and r.json()['subject']=='user:123'

def test_method_bound_assertion_cannot_cross_method():
    with TestClient(app) as client:
        r=client.get('/api/v1/probe',headers={'X-Internal-API-Key':'service-secret','X-Gateway-Principal':signed()})
    assert r.status_code == 401

def test_missing_gateway_secret_fails_closed(monkeypatch):
    token=signed()
    monkeypatch.setattr(settings,'gateway_assertion_secret','')
    with TestClient(app) as client:
        r=client.post('/api/v1/probe',headers={'X-Internal-API-Key':'service-secret','X-Gateway-Principal':token})
    assert r.status_code == 503


def test_path_bound_assertion_cannot_cross_endpoint():
    token = signed(path='/api/v1/other')
    with TestClient(app) as client:
        response = client.post('/api/v1/probe', headers={
            'X-Internal-API-Key': 'service-secret', 'X-Gateway-Principal': token,
        })
    assert response.status_code == 401


@pytest.mark.parametrize('overrides', [
    {'exp': int(time.time()) - 1},
    {'iat': int(time.time()) + 30},
    {'exp': int(time.time()) + 120},
    {'iss': 'untrusted-gateway'},
    {'aud': 'another-api'},
    {'actor_type': 'administrator'},
    {'tenant_id': '00000000-0000-0000-0000-000000000000'},
    {'jti': 'short'},
])
def test_invalid_assertion_claims_are_rejected(overrides):
    token = signed(overrides=overrides)
    with TestClient(app) as client:
        response = client.post('/api/v1/probe', headers={
            'X-Internal-API-Key': 'service-secret', 'X-Gateway-Principal': token,
        })
    assert response.status_code == 401


def test_duplicate_json_claim_is_rejected():
    now = int(time.time())
    tenant = str(uuid4())
    raw = (
        '{"iss":"trusted-gateway","iss":"trusted-gateway",'
        '"aud":"gamma-api","sub":"user:123","actor_type":"user",'
        f'"tenant_id":"{tenant}","tenant_access":true,'
        f'"iat":{now},"exp":{now + 30},'
        '"jti":"assertion-123456","method":"POST","path":"/api/v1/probe"}'
    )
    with TestClient(app) as client:
        response = client.post('/api/v1/probe', headers={
            'X-Internal-API-Key': 'service-secret', 'X-Gateway-Principal': signed_json(raw),
        })
    assert response.status_code == 401


def test_noncanonical_base64url_assertion_is_rejected():
    token = signed()
    encoded, signature = token.split('.')
    with TestClient(app) as client:
        response = client.post('/api/v1/probe', headers={
            'X-Internal-API-Key': 'service-secret',
            'X-Gateway-Principal': encoded + '=' + '.' + signature,
        })
    assert response.status_code == 401


def test_tampered_assertion_signature_is_rejected():
    encoded, signature = signed().split('.')
    replacement = ('A' if signature[0] != 'A' else 'B') + signature[1:]
    with TestClient(app) as client:
        response = client.post('/api/v1/probe', headers={
            'X-Internal-API-Key': 'service-secret',
            'X-Gateway-Principal': encoded + '.' + replacement,
        })
    assert response.status_code == 401

def test_signed_tenant_wins_over_untrusted_tenant_header():
    signed_tenant = uuid4()
    forged_tenant = uuid4()
    token = signed(overrides={'tenant_id': str(signed_tenant)})
    with TestClient(app) as client:
        response = client.post('/api/v1/probe', headers={
            'X-Internal-API-Key': 'service-secret',
            'X-Gateway-Principal': token,
            'X-Tenant-ID': str(forged_tenant),
        })
    assert response.status_code == 200
    assert response.json()['tenant'] == str(signed_tenant)
    assert response.json()['tenant'] != str(forged_tenant)


def test_unsigned_tenant_header_cannot_authenticate():
    with TestClient(app) as client:
        response = client.post('/api/v1/probe', headers={
            'X-Internal-API-Key': 'service-secret',
            'X-Tenant-ID': str(uuid4()),
        })
    assert response.status_code == 401

@pytest.mark.parametrize('bad_subject', ['user:\ud800', 'user:\udfff'])
def test_http_signed_unpaired_surrogate_subject_rejected(bad_subject):
    token = signed(overrides={'sub': bad_subject})
    with TestClient(app) as client:
        response = client.post('/api/v1/probe', headers={
            'X-Internal-API-Key': 'service-secret',
            'X-Gateway-Principal': token,
        })
    assert response.status_code == 401


@pytest.mark.parametrize("duplicate_name", [
    "X-Internal-API-Key", "X-Gateway-Principal", "X-Tenant-ID", "X-Actor-ID",
])
def test_duplicate_identity_headers_are_rejected_before_principal_selection(duplicate_name):
    token = signed()
    headers = [
        ("X-Internal-API-Key", "service-secret"),
        ("X-Gateway-Principal", token),
    ]
    headers.extend([(duplicate_name, "forged-one"), (duplicate_name, "forged-two")])
    with TestClient(app) as client:
        response = client.post("/api/v1/probe", headers=headers)
    assert response.status_code == 401


def test_single_untrusted_tenant_header_does_not_override_signed_tenant():
    tenant = uuid4()
    token = signed(overrides={"tenant_id": str(tenant)})
    with TestClient(app) as client:
        response = client.post("/api/v1/probe", headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": token,
            "X-Tenant-ID": str(uuid4()),
        })
    assert response.status_code == 200
    assert response.json()["tenant"] == str(tenant)


def test_http_replay_rejected():
    headers = {'X-Internal-API-Key': 'service-secret', 'X-Gateway-Principal': signed()}
    with TestClient(app) as client:
        assert client.post('/api/v1/probe', headers=headers).status_code == 200
        assert client.post('/api/v1/probe', headers=headers).status_code == 401


def test_http_replay_store_unavailable(monkeypatch):
    monkeypatch.setattr('app.security.consume_assertion_before_access', AsyncMock(side_effect=RuntimeError('synthetic failure')))
    with TestClient(app) as client:
        response = client.post('/api/v1/probe', headers={'X-Internal-API-Key': 'service-secret', 'X-Gateway-Principal': signed()})
    assert response.status_code == 503
    assert response.json()['detail'] == 'Gateway replay protection unavailable'
