import base64
import hashlib
import hmac
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from app.security import verify_gateway_assertion, require_business_permission
from app.settings import settings

SECRET = "synthetic-test-secret-" * 3
NOW = 1800000000
PATH = "/api/v1/topology/bindings"


def encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign(claims):
    body = encode(json.dumps(claims).encode())
    return body + "." + encode(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())


@pytest.fixture
def claims(monkeypatch):
    monkeypatch.setattr(settings, "gateway_assertion_secret", SECRET)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "synthetic")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)
    return dict(iss="synthetic", aud="gamma", iat=NOW, exp=NOW+30,
                method="GET", path=PATH, sub="test-user", actor_type="user",
                jti="synthetic-assertion", tenant_access=True, tenant_id=str(uuid4()))


def verify(token):
    return verify_gateway_assertion(token, method="GET", path=PATH, now=NOW)


@pytest.mark.parametrize("invalid", [None, "bindings:read", {}, [True], ["*"],
                                      ["unknown"], ["bindings:read", "bindings:read"]])
def test_invalid_signed_permissions(claims, invalid):
    with pytest.raises(HTTPException) as exc:
        verify(sign(dict(claims, business_permissions=invalid)))
    assert exc.value.status_code == 401


def test_missing_permission_defaults_to_deny(claims):
    principal = verify(sign(claims))
    assert principal.business_permissions == ()
    with pytest.raises(HTTPException) as exc:
        require_business_permission(principal, "bindings:read")
    assert exc.value.status_code == 403


def test_signed_permission_and_tampering(claims):
    original = sign(dict(claims, business_permissions=["bindings:read"]))
    require_business_permission(verify(original), "bindings:read")
    altered = sign(dict(claims, business_permissions=["bindings:write"]))
    forged = altered.split(".")[0] + "." + original.split(".")[1]
    with pytest.raises(HTTPException) as exc:
        verify(forged)
    assert exc.value.status_code == 401
