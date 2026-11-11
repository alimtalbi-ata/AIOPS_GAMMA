"""HTTPX mock integration tests for disabled-by-default upstream read adapters."""
from uuid import UUID

import httpx
import pytest
from fastapi import HTTPException

from app.reused import glpi_read, upstream
from app.settings import settings


TENANT = UUID("12345678-1234-4234-8234-123456789abc")
REAL_CLIENT = httpx.AsyncClient


def mock_http(monkeypatch, payload):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=payload, headers={"content-type": "application/json"})

    def factory(*args, **kwargs):
        return REAL_CLIENT(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return requests


def configure_canonical(monkeypatch):
    monkeypatch.setattr(settings, "enable_canonical_reads", True)
    monkeypatch.setattr(settings, "core_read_url", "https://core.example.test")
    monkeypatch.setattr(settings, "canonical_read_token", "test-token")


def configure_glpi(monkeypatch):
    monkeypatch.setattr(settings, "enable_glpi_reads", True)
    monkeypatch.setattr(settings, "glpi_tenant_id", str(TENANT))
    monkeypatch.setattr(settings, "glpi_entity_id", "3")
    monkeypatch.setattr(settings, "glpi_session_token", "test-session")
    monkeypatch.setattr(settings, "glpi_app_token", "test-app")
    monkeypatch.setattr(settings, "glpi_read_url", "https://glpi.example.test")


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    b'{"tenant_id":"12345678-1234-4234-8234-123456789abc","tenant_id":"other"}',
    b'{"tenant_id":"12345678-1234-4234-8234-123456789abc","items":[{"id":1,"id":2}]}',
    b'{"tenant_id":"12345678-1234-4234-8234-123456789abc","value":NaN}',
])
async def test_canonical_rejects_ambiguous_json(monkeypatch, payload):
    configure_canonical(monkeypatch)
    mock_http(monkeypatch, payload)
    with pytest.raises(HTTPException) as exc:
        await upstream.fetch_canonical("core", TENANT)
    assert exc.value.status_code == 502
    assert exc.value.detail == "Canonical upstream unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    b'{"id":7,"entities_id":3,"entities_id":9,"type":1}',
    b'{"id":7,"entities_id":3,"type":1,"status":NaN}',
    b'{"id":7,"entities_id":3,"type":1,"meta":{"id":1,"id":2}}',
])
async def test_glpi_rejects_ambiguous_json(monkeypatch, payload):
    configure_glpi(monkeypatch)
    mock_http(monkeypatch, payload)
    with pytest.raises(HTTPException) as exc:
        await glpi_read.read_glpi_incident(TENANT, 7)
    assert exc.value.status_code == 502
    assert exc.value.detail == "GLPI upstream unavailable"


@pytest.mark.asyncio
async def test_canonical_accepts_valid_attestation(monkeypatch):
    configure_canonical(monkeypatch)
    requests = mock_http(monkeypatch, b'{"tenant_id":"12345678-1234-4234-8234-123456789abc","items":[]}')
    result = await upstream.fetch_canonical("core", TENANT)
    assert result["items"] == []
    assert requests[0].headers["X-Tenant-Id"] == str(TENANT)
    assert requests[0].method == "GET"


@pytest.mark.asyncio
async def test_glpi_accepts_valid_entity_and_projects(monkeypatch):
    configure_glpi(monkeypatch)
    requests = mock_http(monkeypatch, b'{"id":7,"entities_id":3,"type":1,"status":2,"private":"do-not-return"}')
    result = await glpi_read.read_glpi_incident(TENANT, 7)
    assert result["read_only"] is True
    assert "private" not in result
    assert requests[0].method == "GET"
