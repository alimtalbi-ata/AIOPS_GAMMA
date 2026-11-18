from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.reused.investigation import InvestigationPreview, evaluate_investigation
from app.settings import settings


def signed_preview_headers(monkeypatch, tenant):
    import base64
    import hashlib
    import hmac
    import json
    import time

    secret = "s" * 48
    monkeypatch.setattr(settings, "gateway_assertion_secret", secret)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "test-gateway")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-api")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)
    now = int(time.time())
    claims = {"iss": "test-gateway", "aud": "gamma-api", "sub": "user:preview-test",
              "actor_type": "user", "tenant_id": str(tenant), "tenant_access": True,
              "iat": now, "exp": now + 30, "jti": uuid4().hex,
              "method": "POST", "path": "/api/v1/incidents/investigation/preview"}
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    signature = base64.urlsafe_b64encode(hmac.new(secret.encode(), encoded, hashlib.sha256).digest()).rstrip(b"=")
    return {"X-Internal-Api-Key": "test-secret",
            "X-Gateway-Principal": (encoded + b"." + signature).decode()}



def sample(tenant, **kwargs):
    data = {
        "tenant_id": tenant,
        "incident_id": "INC-123",
        "started_at": datetime(2026, 11, 9, tzinfo=timezone.utc),
        "evidence": [{
            "ref_id": "trace:123", "source": "trace",
            "observed_at": datetime(2026, 11, 9, tzinfo=timezone.utc),
        }],
        "hypotheses": [{
            "hypothesis_id": "h1", "summary": "Possible timeout",
            "supporting_refs": ["trace:123"], "verdict": "supported",
        }],
    }
    data.update(kwargs)
    return InvestigationPreview(**data)


def test_evidence_preview_is_explicitly_non_authoritative():
    tenant = uuid4()
    result = evaluate_investigation(sample(tenant), tenant)
    assert result["hypothesis_evidence_coverage_pct"] == 100
    assert result["citation_references_resolved"] is True
    assert result["citations_source_verified"] is False
    assert result["human_adjudicated"] is False
    assert result["live_execution_authorized"] is False


def test_empty_hypotheses_do_not_invent_success():
    tenant = uuid4()
    result = evaluate_investigation(sample(tenant, hypotheses=[]), tenant)
    assert result["hypothesis_evidence_coverage_pct"] is None
    assert result["unknown_hypotheses"] == 0


@pytest.mark.parametrize("overrides", [
    {"evidence": []},
    {"evidence": [{"ref_id": "trace:123", "source": "trace", "observed_at": "2026-11-09T00:00:00"}]},
    {"evidence": [{"ref_id": "trace:123", "source": "trace", "observed_at": "2026-11-09T00:00:00Z", "raw_prompt": "secret"}]},
    {"hypotheses": [{"hypothesis_id": "h1", "summary": "guess", "verdict": "supported"}]},
    {"hypotheses": [{"hypothesis_id": "h1", "summary": "guess", "verdict": "unknown", "supporting_refs": ["missing"]}]},
    {"hypotheses": [{"hypothesis_id": "h1", "summary": "guess", "verdict": "unknown", "supporting_refs": ["trace:123"], "contradicting_refs": ["trace:123"]}]},
    {"started_at": "2026-11-09T00:00:00"},
])
def test_invalid_investigation_is_rejected(overrides):
    with pytest.raises(ValidationError):
        sample(uuid4(), **overrides)


def test_tenant_mismatch_is_rejected():
    with pytest.raises(PermissionError, match="Cross-tenant"):
        evaluate_investigation(sample(uuid4()), uuid4())


def test_endpoint_requires_auth(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    tenant = uuid4()
    with TestClient(app) as client:
        response = client.post("/api/v1/incidents/investigation/preview",
                               json=sample(tenant).model_dump(mode="json"))
    assert response.status_code == 401


def test_endpoint_cross_tenant_denied(monkeypatch, replay_unit):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    tenant = uuid4()
    with TestClient(app) as client:
        response = client.post("/api/v1/incidents/investigation/preview",
                               json=sample(tenant).model_dump(mode="json"),
                               headers=signed_preview_headers(monkeypatch, uuid4()))
    assert response.status_code == 403


def test_endpoint_returns_safe_projection(monkeypatch, replay_unit):
    monkeypatch.setattr(settings, "internal_api_key", "test-secret")
    tenant = uuid4()
    with TestClient(app) as client:
        response = client.post("/api/v1/incidents/investigation/preview",
                               json=sample(tenant).model_dump(mode="json"),
                               headers=signed_preview_headers(monkeypatch, tenant))
    assert response.status_code == 200
    assert response.json()["data_source"] == "caller_supplied_preview"
