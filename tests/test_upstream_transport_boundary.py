"""Transport boundary regression cases for Canonical and GLPI adapters."""
from uuid import UUID

import httpx
import pytest
from fastapi import HTTPException

from app.reused import glpi_read, upstream
from app.settings import settings
from test_upstream_fail_closed_extra import canonical, glpi, stub

TENANT = UUID("12345678-1234-4234-8234-123456789abc")


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [
    "http://core.example.test",
    "https://user:pass@core.example.test",
    "https://core.example.test/other",
    "https://localhost",
])
async def test_canonical_bad_origin_no_network(monkeypatch, origin):
    canonical(monkeypatch)
    monkeypatch.setattr(settings, "core_read_url", origin)
    requests = stub(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await upstream.fetch_canonical("core", TENANT)
    assert exc.value.status_code == 503
    assert not requests


@pytest.mark.asyncio
async def test_canonical_wrong_content_type_rejected(monkeypatch):
    canonical(monkeypatch)
    stub(monkeypatch, content=b'{"tenant_id":"12345678-1234-4234-8234-123456789abc"}', content_type="text/html")
    with pytest.raises(HTTPException) as exc:
        await upstream.fetch_canonical("core", TENANT)
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_glpi_wrong_content_type_rejected(monkeypatch):
    glpi(monkeypatch)
    stub(monkeypatch, content=b'{"id":7,"entities_id":3,"type":1}', content_type="text/html")
    with pytest.raises(HTTPException) as exc:
        await glpi_read.read_glpi_incident(TENANT, 7)
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_canonical_network_failure_sanitized(monkeypatch):
    canonical(monkeypatch)
    real_client = httpx.AsyncClient

    def handler(request):
        raise httpx.ConnectError("internal-secret-hostname", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(HTTPException) as exc:
        await upstream.fetch_canonical("core", TENANT)
    assert exc.value.status_code == 502
    assert "internal-secret-hostname" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_glpi_network_failure_sanitized(monkeypatch):
    glpi(monkeypatch)
    real_client = httpx.AsyncClient

    def handler(request):
        raise httpx.ConnectError("internal-secret-hostname", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(HTTPException) as exc:
        await glpi_read.read_glpi_incident(TENANT, 7)
    assert exc.value.status_code == 502
    assert "internal-secret-hostname" not in str(exc.value.detail)
