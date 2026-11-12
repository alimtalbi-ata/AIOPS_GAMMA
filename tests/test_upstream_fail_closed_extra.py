"""Negative HTTP contract cases against exact GitHub upstream adapter files."""
from uuid import UUID
import httpx
import pytest
from fastapi import HTTPException
from app.reused import upstream, glpi_read
from app.settings import settings

TENANT = UUID('12345678-1234-4234-8234-123456789abc')
REAL_CLIENT = httpx.AsyncClient


def stub(monkeypatch, *, status=200, content=b'{}', content_type='application/json'):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, content=content, headers={'content-type': content_type})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda *a, **kw: REAL_CLIENT(*a, transport=httpx.MockTransport(handler), **kw))
    return requests


def canonical(monkeypatch):
    monkeypatch.setattr(settings, 'enable_canonical_reads', True)
    monkeypatch.setattr(settings, 'core_read_url', 'https://core.example.test')
    monkeypatch.setattr(settings, 'canonical_read_token', 'test-token')


def glpi(monkeypatch):
    monkeypatch.setattr(settings, 'enable_glpi_reads', True)
    monkeypatch.setattr(settings, 'glpi_tenant_id', str(TENANT))
    monkeypatch.setattr(settings, 'glpi_entity_id', '3')
    monkeypatch.setattr(settings, 'glpi_session_token', 'test-session')
    monkeypatch.setattr(settings, 'glpi_app_token', 'test-app')
    monkeypatch.setattr(settings, 'glpi_read_url', 'https://glpi.example.test')


@pytest.mark.asyncio
async def test_canonical_disabled_never_contacts_upstream(monkeypatch):
    monkeypatch.setattr(settings, 'enable_canonical_reads', False)
    monkeypatch.setattr(settings, 'canonical_read_token', 'test-token')
    requests = stub(monkeypatch)
    with pytest.raises(HTTPException) as e:
        await upstream.fetch_canonical('core', TENANT)
    assert e.value.status_code == 503
    assert not requests


@pytest.mark.asyncio
async def test_glpi_wrong_tenant_never_contacts_upstream(monkeypatch):
    glpi(monkeypatch)
    requests = stub(monkeypatch)
    with pytest.raises(HTTPException) as e:
        await glpi_read.read_glpi_incident(UUID('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'), 7)
    assert e.value.status_code == 403
    assert not requests


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [301, 302, 307, 308])
async def test_canonical_redirects_are_not_followed(monkeypatch, status):
    canonical(monkeypatch)
    requests = stub(monkeypatch, status=status)
    with pytest.raises(HTTPException) as e:
        await upstream.fetch_canonical('core', TENANT)
    assert e.value.status_code == 503
    assert not requests


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [301, 302, 307, 308])
async def test_glpi_redirects_are_not_followed(monkeypatch, status):
    glpi(monkeypatch)
    requests = stub(monkeypatch, status=status)
    with pytest.raises(HTTPException) as e:
        await glpi_read.read_glpi_incident(TENANT, 7)
    assert e.value.status_code == 502
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_canonical_missing_tenant_attestation_rejected(monkeypatch):
    canonical(monkeypatch)
    stub(monkeypatch, content=b'{"items":[]}')
    with pytest.raises(HTTPException) as e:
        await upstream.fetch_canonical('core', TENANT)
    assert e.value.status_code == 503


@pytest.mark.asyncio
async def test_glpi_wrong_entity_rejected(monkeypatch):
    glpi(monkeypatch)
    stub(monkeypatch, content=b'{"id":7,"entities_id":4,"type":1}')
    with pytest.raises(HTTPException) as e:
        await glpi_read.read_glpi_incident(TENANT, 7)
    assert e.value.status_code == 502


@pytest.mark.asyncio
async def test_canonical_oversize_rejected(monkeypatch):
    canonical(monkeypatch)
    stub(monkeypatch, content=b' ' * (upstream.MAX_BYTES + 1))
    with pytest.raises(HTTPException) as e:
        await upstream.fetch_canonical('core', TENANT)
    assert e.value.status_code == 503


@pytest.mark.asyncio
async def test_glpi_oversize_rejected(monkeypatch):
    glpi(monkeypatch)
    stub(monkeypatch, content=b' ' * (upstream.MAX_BYTES + 1))
    with pytest.raises(HTTPException) as e:
        await glpi_read.read_glpi_incident(TENANT, 7)
    assert e.value.status_code == 502
