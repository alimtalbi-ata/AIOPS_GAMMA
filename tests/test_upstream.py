from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.reused import upstream


@pytest.mark.parametrize("url", [
    "http://example.com", "https://user:pw@example.com",
    "https://example.com/api", "https://example.com?x=1",
    "https://localhost", "https://example.com#fragment",
])
def test_reject_unsafe_origins(url):
    with pytest.raises(ValueError):
        upstream.validate_origin(url)


def test_accept_fixed_https_origin():
    assert upstream.validate_origin("https://core.internal:8443/") == "https://core.internal:8443"


@pytest.mark.asyncio
async def test_disabled_by_default():
    with pytest.raises(HTTPException) as exc:
        await upstream.fetch_canonical("core", uuid4())
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_unknown_resource_is_not_arbitrary_url():
    with pytest.raises(HTTPException) as exc:
        await upstream.fetch_canonical("http://attacker", uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("status,payload,ctype,expected", [
    (200, b'{"tenant_id":"WRONG"}', "application/json", 502),
    (200, b'{"hello":true}', "application/json", 502),
    (200, b'[]', "application/json", 502),
    (200, b'{"x":1}', "text/html", 502),
    (302, b'', "text/html", 502),
    (200, b'x' * (upstream.MAX_BYTES + 1), "application/json", 502),
])
async def test_fail_closed_upstream(monkeypatch, status, payload, ctype, expected):
    tenant = uuid4()
    monkeypatch.setattr(upstream.settings, "enable_canonical_reads", True)
    monkeypatch.setattr(upstream.settings, "canonical_read_token", "test-secret")
    monkeypatch.setattr(upstream.settings, "core_read_url", "https://core.internal")
    original = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        transport = httpx.MockTransport(
            lambda req: httpx.Response(status, content=payload, headers={"content-type": ctype})
        )
        return original(*args, transport=transport, **kwargs)

    monkeypatch.setattr(upstream.httpx, "AsyncClient", fake_client)
    with pytest.raises(HTTPException) as exc:
        await upstream.fetch_canonical("core", tenant)
    assert exc.value.status_code == expected


@pytest.mark.asyncio
async def test_valid_tenant_attested_response(monkeypatch):
    tenant = uuid4()
    monkeypatch.setattr(upstream.settings, "enable_canonical_reads", True)
    monkeypatch.setattr(upstream.settings, "canonical_read_token", "test-secret")
    monkeypatch.setattr(upstream.settings, "core_read_url", "https://core.internal")
    original = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        def handle(req):
            assert req.method == "GET"
            assert req.url.path == "/api/v1/incidents"
            assert req.headers["X-Tenant-Id"] == str(tenant)
            return httpx.Response(200, json={"tenant_id": str(tenant), "incidents": []})
        return original(*args, transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(upstream.httpx, "AsyncClient", fake_client)
    result = await upstream.fetch_canonical("core", tenant)
    assert result["incidents"] == []
