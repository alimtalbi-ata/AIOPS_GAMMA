"""HTTP dependency boundary against exact GitHub security/settings modules; isolated FastAPI harness."""
import base64
import hashlib
import hmac
import json
import time
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
    monkeypatch.setattr(settings, 'internal_api_key', 'service-secret')
    monkeypatch.setattr(settings, 'gateway_assertion_secret', 's'*48)
    monkeypatch.setattr(settings, 'gateway_assertion_issuer', 'trusted-gateway')
    monkeypatch.setattr(settings, 'gateway_assertion_audience', 'gamma-api')
    monkeypatch.setattr(settings, 'gateway_assertion_max_ttl_seconds', 60)

def signed(*, method='POST', path='/api/v1/probe', tenant_access=True):
    now = int(time.time())
    claims = {'iss':'trusted-gateway','aud':'gamma-api','sub':'user:123',
              'actor_type':'user','tenant_id':str(uuid4()),'tenant_access':tenant_access,
              'iat':now,'exp':now+30,'jti':'assertion-123456', 'method':method,'path':path}
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b'=').decode()
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
