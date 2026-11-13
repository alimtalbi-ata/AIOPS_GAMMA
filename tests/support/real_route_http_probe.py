"""Isolated real main.py + security.py HTTP probe. Never import from normal suite."""
import base64
import hashlib
import hmac
import json
import sys
import time
import types
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel


def stub(name, **values):
    module = types.ModuleType(name)
    module.__dict__.update(values)
    sys.modules[name] = module


class Empty(BaseModel):
    pass


class EvidenceInput(BaseModel):
    tenant_id: str


class DBModel:
    pass


async def forbidden_db():
    raise AssertionError("No DB access permitted in HTTP isolation probe")


stub("app.db", get_session=forbidden_db)
stub("app.models", **{name: DBModel for name in ("Evidence", "InboxEvent", "OutboxEvent", "ServiceBinding")})
stub("app.opensearch_adapter", search_logs=MagicMock())
stub("app.schemas", **{name: Empty for name in ("AlertPayload", "BindingIn", "EvidenceIn", "LogSearchRequest")})
stub("app.reused.impact", estimate_impact=MagicMock())
stub("app.reused.policy", RemediationProposal=Empty, evaluate=MagicMock())
stub("app.reused.correlation", CorrelationPreview=Empty, correlate=MagicMock())
stub("app.reused.upstream", ALLOWED_RESOURCES={"incidents"}, fetch_canonical=MagicMock())
stub("app.reused.itil", ITILPreviewRequest=Empty, preview_itil_workflow=MagicMock())
stub("app.reused.itsm_contract", IncidentSyncPreview=Empty, plan_incident_sync=MagicMock())
stub("app.reused.glpi_read", read_glpi_incident=MagicMock())
stub("app.reused.llm_kpi", LLMKPIRequest=Empty, calculate_llm_kpis=MagicMock())
stub("app.reused.investigation", InvestigationPreview=Empty, evaluate_investigation=MagicMock())
stub("app.reused.evidence", EvidenceInput=EvidenceInput, normalize=MagicMock())
stub("app.reused.correlation_evidence", CorrelationEvidencePreview=Empty, preview=MagicMock())
stub("app.demo", synthetic_correlation_demo=lambda: {"mode": "synthetic_demo"},
     synthetic_investigation_demo=lambda: {"mode": "synthetic_demo"})

from app.main import app
from app.settings import settings


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "service-secret")
    monkeypatch.setattr(settings, "gateway_assertion_secret", "s" * 48)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "trusted-gateway")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-api")


PUBLIC = {"/api/v1/health/live", "/api/v1/demo/correlation", "/api/v1/demo/investigation"}
PROTECTED = [
    (next(iter(route.methods)), route.path)
    for route in app.routes
    if route.path.startswith("/api/v1/") and route.path not in PUBLIC
]
assert len(PROTECTED) == 18, "Explicit route inventory review required"


@pytest.mark.parametrize("method,path", PROTECTED)
def test_unsigned_actor_rejected(method, path):
    concrete = (path.replace("{incident_id}", "INC-1")
                    .replace("{resource}", "incidents")
                    .replace("{ticket_id}", "1"))
    with TestClient(app) as client:
        response = client.request(method, concrete, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Tenant-ID": str(uuid4()),
        }, json={})
    assert response.status_code == 401, (method, path, response.text)
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", sorted(PUBLIC))
def test_public_route(path):
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200
    if path != "/api/v1/health/live":
        assert response.headers["cache-control"] == "no-store"


def signed(method, path):
    now = int(time.time())
    claims = {
        "iss": "trusted-gateway", "aud": "gamma-api", "sub": "user:123",
        "actor_type": "user", "tenant_id": str(uuid4()), "tenant_access": True,
        "iat": now, "exp": now + 30, "jti": "probe-assertion-123",
        "method": method, "path": path,
    }
    raw = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(hmac.new(b"s" * 48, raw, hashlib.sha256).digest()).rstrip(b"=")
    return (raw + b"." + sig).decode()


def headers(path, signed_path=None):
    return {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": signed("POST", signed_path or path),
    }


def test_signed_actor_reaches_metrics_route():
    path = "/api/v1/observability/metrics/query"
    with TestClient(app) as client:
        response = client.post(path, headers=headers(path))
    assert response.status_code == 501
    assert response.headers["cache-control"] == "no-store"


def test_wrong_signed_path_rejected():
    path = "/api/v1/observability/metrics/query"
    with TestClient(app) as client:
        response = client.post(path, headers=headers(path, "/api/v1/other"))
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_cross_tenant_evidence_preview_rejected():
    path = "/api/v1/incidents/evidence/preview"
    with TestClient(app) as client:
        response = client.post(path, headers=headers(path),
                               json={"items": [{"tenant_id": str(uuid4())}]})
    assert response.status_code == 403, response.text
    assert response.headers["cache-control"] == "no-store"


def test_forged_tenant_header_cannot_override_signed_actor():
    path = "/api/v1/observability/metrics/query"
    forged = headers(path)
    forged["X-Tenant-ID"] = str(uuid4())
    with TestClient(app) as client:
        response = client.post(path, headers=forged)
    assert response.status_code == 501
    assert response.headers["cache-control"] == "no-store"

def test_tampered_signed_actor_rejected():
    path = "/api/v1/observability/metrics/query"
    token = signed("POST", path)
    payload, signature = token.split(".")
    tampered = payload + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
    with TestClient(app) as client:
        response = client.post(path, headers={
            "X-Internal-API-Key": "service-secret",
            "X-Gateway-Principal": tampered,
        })
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
