from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.reused import glpi_read


@pytest.mark.asyncio
async def test_disabled_by_default(monkeypatch):
    monkeypatch.setattr(glpi_read.settings, "enable_glpi_reads", False)
    with pytest.raises(HTTPException) as exc:
        await glpi_read.read_glpi_incident(uuid4(), 12)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_cross_tenant_denied_before_network(monkeypatch):
    monkeypatch.setattr(glpi_read.settings, "enable_glpi_reads", True)
    monkeypatch.setattr(glpi_read.settings, "glpi_tenant_id", str(uuid4()))
    with pytest.raises(HTTPException) as exc:
        await glpi_read.read_glpi_incident(uuid4(), 12)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,status", [
    ({"id": 12, "entities_id": 8, "type": 1, "status": 2}, 200),
    ({"id": 13, "entities_id": 7, "type": 1}, 502),
    ({"id": 12, "entities_id": 9, "type": 1}, 502),
    ({"id": 12}, 502),
    ({"id": 12, "entities_id": 8, "type": 2}, 502),
    ({"id": 12, "entities_id": 8, "type": True}, 502),
    ([{"id": 12, "entities_id": 8}], 502),
])
async def test_entity_binding_and_safe_projection(monkeypatch, payload, status):
    tenant = uuid4()
    for name, value in {
        "enable_glpi_reads": True,
        "glpi_tenant_id": str(tenant),
        "glpi_entity_id": "8",
        "glpi_read_url": "https://glpi.internal",
        "glpi_session_token": "test-session",
        "glpi_app_token": "test-app",
    }.items():
        monkeypatch.setattr(glpi_read.settings, name, value)
    original = httpx.AsyncClient

    def mock_client(*args, **kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False

        def handle(request):
            assert request.method == "GET"
            assert request.url.path == "/apirest.php/Ticket/12"
            assert request.headers["Session-Token"] == "test-session"
            return httpx.Response(200, json=payload)
        return original(*args, transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(glpi_read.httpx, "AsyncClient", mock_client)
    if status == 502:
        with pytest.raises(HTTPException) as exc:
            await glpi_read.read_glpi_incident(tenant, 12)
        assert exc.value.status_code == 502
    else:
        result = await glpi_read.read_glpi_incident(tenant, 12)
        assert result["ticket_id"] == 12
        assert result["entity_id"] == 8
        assert result["read_only"] is True
        assert "name" not in result
