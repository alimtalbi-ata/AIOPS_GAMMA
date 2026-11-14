from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.reused import glpi_read


@pytest.mark.asyncio
async def test_disabled_by_default(monkeypatch):
    monkeypatch.setattr(glpi_read.settings, "enable_glpi_reads", False)
    with pytest.raises(HTTPException) as exc:
        await glpi_read._read_glpi_incident_unqualified(uuid4(), 12)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_cross_tenant_denied_before_network(monkeypatch):
    monkeypatch.setattr(glpi_read.settings, "enable_glpi_reads", True)
    monkeypatch.setattr(glpi_read.settings, "glpi_tenant_id", str(uuid4()))
    with pytest.raises(HTTPException) as exc:
        await glpi_read._read_glpi_incident_unqualified(uuid4(), 12)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,status", [
    ({"id": 12, "entities_id": 8, "type": 1, "status": 2}, 200),
    ({"id": 13, "entities_id": 7, "type": 1}, 502),
    ({"id": 12, "entities_id": 9, "type": 1}, 502),
    ({"id": 12}, 502),
    ({"id": 12, "entities_id": 8, "type": 2}, 502),
    ({"id": 12, "entities_id": 8, "type": True}, 502),
    ({"id": 12, "entities_id": 8, "type": 1, "status": "2"}, 502),
    ({"id": True, "entities_id": 8, "type": 1}, 502),
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
            await glpi_read._read_glpi_incident_unqualified(tenant, 12)
        assert exc.value.status_code == 502
    else:
        result = await glpi_read._read_glpi_incident_unqualified(tenant, 12)
        assert result["ticket_id"] == 12
        assert result["entity_id"] == 8
        assert result["read_only"] is True
        assert "name" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("ticket_id", [0, -1, True, "12"])
async def test_invalid_ticket_id_rejected_before_network(monkeypatch, ticket_id):
    monkeypatch.setattr(glpi_read.settings, "enable_glpi_reads", True)
    with pytest.raises(HTTPException) as exc:
        await glpi_read._read_glpi_incident_unqualified(uuid4(), ticket_id)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("http_status", [301, 302, 401, 403, 404, 429, 500])
async def test_upstream_non_200_is_fail_closed(monkeypatch, http_status):
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
        def handle(request):
            return httpx.Response(http_status, headers={"Location": "https://evil.invalid/"})
        return original(*args, transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(glpi_read.httpx, "AsyncClient", mock_client)
    with pytest.raises(HTTPException) as exc:
        await glpi_read._read_glpi_incident_unqualified(tenant, 12)
    assert exc.value.status_code == 502
    assert "test-session" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_upstream_non_json_rejected(monkeypatch):
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
        return original(*args, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="<html>not json</html>")
        ), **kwargs)

    monkeypatch.setattr(glpi_read.httpx, "AsyncClient", mock_client)
    with pytest.raises(HTTPException) as exc:
        await glpi_read._read_glpi_incident_unqualified(tenant, 12)
    assert exc.value.status_code == 502


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [
    "http://glpi.internal",
    "https://user:password@glpi.internal",
    "https://glpi.internal/other/path",
    "https://glpi.internal?redirect=https://evil.invalid",
    "https://glpi.internal#fragment",
    "https://localhost",
    "https://glpi.internal:invalid",
    "https://glpi.internal:99999",
    "https://glpi.internal:0",
])
async def test_unsafe_glpi_origin_rejected_before_network(monkeypatch, origin):
    tenant = uuid4()
    for name, value in {
        "enable_glpi_reads": True,
        "glpi_tenant_id": str(tenant),
        "glpi_entity_id": "8",
        "glpi_read_url": origin,
        "glpi_session_token": "test-session",
        "glpi_app_token": "test-app",
    }.items():
        monkeypatch.setattr(glpi_read.settings, name, value)

    def no_network(*args, **kwargs):
        raise AssertionError("Invalid GLPI origin must not trigger a network call")

    monkeypatch.setattr(glpi_read.httpx, "AsyncClient", no_network)
    with pytest.raises(HTTPException) as exc:
        await glpi_read._read_glpi_incident_unqualified(tenant, 12)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("body,content_type", [
    (b"x" * (glpi_read.MAX_BYTES + 1), "application/json"),
    (b"{invalid-json", "application/json"),
    (b"[]", "application/json"),
])
async def test_glpi_response_size_and_json_shape_fail_closed(monkeypatch, body, content_type):
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
        return original(*args, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=body,
                                           headers={"content-type": content_type})
        ), **kwargs)

    monkeypatch.setattr(glpi_read.httpx, "AsyncClient", mock_client)
    with pytest.raises(HTTPException) as exc:
        await glpi_read._read_glpi_incident_unqualified(tenant, 12)
    assert exc.value.status_code == 502


@pytest.mark.asyncio
@pytest.mark.parametrize("entity_id", ["-1", "not-an-int", "8.5"])
async def test_invalid_server_entity_configuration_fails_before_network(monkeypatch, entity_id):
    tenant = uuid4()
    for name, value in {
        "enable_glpi_reads": True,
        "glpi_tenant_id": str(tenant),
        "glpi_entity_id": entity_id,
        "glpi_read_url": "https://glpi.internal",
        "glpi_session_token": "test-session",
        "glpi_app_token": "test-app",
    }.items():
        monkeypatch.setattr(glpi_read.settings, name, value)

    def no_network(*args, **kwargs):
        raise AssertionError("Invalid entity config must not trigger network")

    monkeypatch.setattr(glpi_read.httpx, "AsyncClient", no_network)
    with pytest.raises(HTTPException) as exc:
        await glpi_read._read_glpi_incident_unqualified(tenant, 12)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_setting", [
    "glpi_read_url", "glpi_entity_id", "glpi_session_token", "glpi_app_token",
])
async def test_missing_glpi_configuration_fails_before_network(monkeypatch, missing_setting):
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
    monkeypatch.setattr(glpi_read.settings, missing_setting, "")

    def no_network(*args, **kwargs):
        raise AssertionError("Incomplete GLPI config must not trigger network")

    monkeypatch.setattr(glpi_read.httpx, "AsyncClient", no_network)
    with pytest.raises(HTTPException) as exc:
        await glpi_read._read_glpi_incident_unqualified(tenant, 12)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_public_glpi_read_never_reaches_transport_without_qualified_acl(monkeypatch, enabled):
    monkeypatch.setattr(glpi_read.settings, "enable_glpi_reads", enabled)
    def no_network(*args, **kwargs):
        raise AssertionError("Public GLPI read must not make network requests")
    monkeypatch.setattr(glpi_read.httpx, "AsyncClient", no_network)
    with pytest.raises(HTTPException) as exc:
        await glpi_read.read_glpi_incident(uuid4(), 12)
    assert exc.value.status_code == 503
    assert "ACL not qualified" in str(exc.value.detail)


@pytest.mark.asyncio
@pytest.mark.parametrize("ticket_id", [0, -1, True, "12"])
async def test_public_glpi_read_rejects_invalid_ticket_before_acl(ticket_id):
    with pytest.raises(HTTPException) as exc:
        await glpi_read.read_glpi_incident(uuid4(), ticket_id)
    assert exc.value.status_code == 422
