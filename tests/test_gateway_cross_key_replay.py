"""Synthetic signed assertions, shared disposable PostgreSQL replay state."""
import asyncio
import hashlib
import os
import time
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.gateway_replay import consume_assertion_before_access
from app.security import verify_gateway_assertion
from app.settings import settings
from test_signed_business_permissions import sign, SECRET, PATH


@pytest.mark.asyncio
async def test_concurrent_cross_key_replay(monkeypatch):
    if os.getenv("GAMMA_TEST_DISPOSABLE") != "1":
        pytest.skip("Disposable database required")
    second = "synthetic-second-key-" * 3
    issuer = "synthetic-cross-key"
    now = int(time.time())
    monkeypatch.setattr(settings, "gateway_assertion_secret", "")
    monkeypatch.setattr(settings, "gateway_assertion_keys", {"K1": SECRET, "K2": second})
    monkeypatch.setattr(settings, "gateway_assertion_issuer", issuer)
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)
    claims = dict(iss=issuer, aud="gamma", iat=now, exp=now+30,
                  method="GET", path=PATH, sub="synthetic", actor_type="user",
                  jti=str(uuid4()), tenant_access=True, tenant_id=str(uuid4()),
                  business_permissions=["bindings:read"])
    principals = [
        verify_gateway_assertion(sign(dict(claims, kid=k), secret),
                                 method="GET", path=PATH, now=now)
        for k, secret in (("K1", SECRET), ("K2", second))
    ]
    engine = create_async_engine(os.environ["GAMMA_TEST_DATABASE_URL"], pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine)
    ready = asyncio.Barrier(2)
    digest = hashlib.sha256((issuer + "\x00" + claims["jti"]).encode()).hexdigest()

    async def consume(p, synchronize=False):
        async with factory() as session:
            await session.execute(text("SELECT 1"))
            if synchronize:
                await ready.wait()
            return await consume_assertion_before_access(
                session, issuer=issuer, assertion_id=p.assertion_id, expires_at=p.expires_at)
    try:
        results = await asyncio.wait_for(asyncio.gather(
            *(consume(p, True) for p in principals)), timeout=15)
        assert sorted(results) == [False, True]
        assert not await consume(principals[0])
        assert not await consume(principals[1])
        # The disposable database is destroyed by CI. Never delete live replay
        # reservations using runtime credentials, even for fixture teardown.
        with pytest.raises(DBAPIError) as denied:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM gateway_assertion_replay WHERE assertion_digest=:digest"), {"digest": digest})
        assert getattr(denied.value.orig, "sqlstate", None) == "42501"
        assert not await consume(principals[0])
    finally:
        await engine.dispose()
