from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.reused import upstream


@pytest.mark.parametrize("url", [
    "http://example.com", "https://user:pw@example.com",
    "https://example.com/api", "https://example.com?x=1",
    "https://localhost", "https://example.com#fragment",
    "https://example.com:invalid", "https://example.com:99999",
    "https://example.com:0",
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
@pytest.mark.parametrize("resource", ["core", "evidence", "twin"])
async def test_canonical_reads_refuse_even_with_flag_and_tenant_echo(monkeypatch, resource):
    """An echoed tenant ID and service token cannot authorize a user resource."""
    tenant = uuid4()
    monkeypatch.setattr(upstream.settings, "enable_canonical_reads", True)
    monkeypatch.setattr(upstream.settings, "canonical_read_token", "test-secret")
    for setting in ("core_read_url", "evidence_read_url", "twin_read_url"):
        monkeypatch.setattr(upstream.settings, setting, "https://upstream.internal")

    def forbid_network(*args, **kwargs):
        raise AssertionError("canonical upstream network I/O before actor/resource ACL")

    monkeypatch.setattr(upstream.httpx, "AsyncClient", forbid_network)
    with pytest.raises(HTTPException) as exc:
        await upstream.fetch_canonical(resource, tenant)
    assert exc.value.status_code == 503
    assert exc.value.detail == "Canonical actor/tenant/resource ACL not qualified"


@pytest.mark.asyncio
async def test_canonical_reads_reject_unknown_resource_before_network(monkeypatch):
    monkeypatch.setattr(upstream.settings, "enable_canonical_reads", True)
    monkeypatch.setattr(upstream.httpx, "AsyncClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    with pytest.raises(HTTPException) as exc:
        await upstream.fetch_canonical("arbitrary", uuid4())
    assert exc.value.status_code == 404
