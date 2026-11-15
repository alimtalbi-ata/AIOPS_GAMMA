"""P1: signed actor-to-service authorization must precede OpenSearch network I/O."""
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi import HTTPException, Response

from app.main import logs
from app.schemas import LogSearchRequest, TimeWindow
from app.security import Principal
from app.settings import settings


def request():
    return LogSearchRequest(
        service_name="checkout",
        window=TimeWindow(
            start=datetime(2026, 11, 15, 12, tzinfo=timezone.utc),
            end=datetime(2026, 11, 15, 13, tzinfo=timezone.utc),
        ),
    )


def actor(grants=()):
    return Principal(
        tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
        subject="user:123", actor_type="user", assertion_id="assertion-123",
        expires_at=9999999999, log_service_grants=grants,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("grants", [(), ("billing",), ("Checkout",)])
async def test_service_without_exact_signed_grant_denied_before_network(monkeypatch, grants):
    monkeypatch.setattr(settings, "enable_opensearch", True)
    async def forbidden(*args, **kwargs):
        raise AssertionError("OpenSearch must not be contacted")
    monkeypatch.setattr("app.main.search_logs", forbidden)
    with pytest.raises(HTTPException) as exc:
        await logs(request(), Response(), actor(grants))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_exact_signed_grant_allows_scoped_adapter_call(monkeypatch):
    monkeypatch.setattr(settings, "enable_opensearch", True)
    observed = []
    async def fake_search(tenant_id, req):
        observed.append((tenant_id, req.service_name))
        return {"hits": {"hits": []}}
    monkeypatch.setattr("app.main.search_logs", fake_search)
    response = Response()
    assert await logs(request(), response, actor(("checkout",))) == {"hits": {"hits": []}}
    assert observed == [("11111111-1111-4111-8111-111111111111", "checkout")]
    assert response.headers["Cache-Control"] == "no-store"
