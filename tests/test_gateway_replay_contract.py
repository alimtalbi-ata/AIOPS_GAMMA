"""Unit contract tests for proposed shared replay store, not live DB."""
import pytest
from sqlalchemy.exc import OperationalError

from app.gateway_replay import reserve_assertion_once


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self):
        self.seen = set()
        self.digests = []

    async def execute(self, statement, params):
        assert "ON CONFLICT (assertion_digest) DO NOTHING" in str(statement)
        digest = params["digest"]
        self.digests.append(digest)
        if digest in self.seen:
            return FakeResult(None)
        self.seen.add(digest)
        return FakeResult(digest)


@pytest.mark.asyncio
async def test_replay_is_reserved_only_once():
    store = FakeSession()
    assert await reserve_assertion_once(store, issuer="gateway", assertion_id="jti-12345678", expires_at=2000)
    assert not await reserve_assertion_once(store, issuer="gateway", assertion_id="jti-12345678", expires_at=2000)
    assert await reserve_assertion_once(store, issuer="other-gateway", assertion_id="jti-12345678", expires_at=2000)
    assert len(store.digests[0]) == 64
    assert "jti-12345678" not in store.digests[0]


@pytest.mark.asyncio
async def test_invalid_reservation_is_rejected():
    store = FakeSession()
    with pytest.raises(ValueError):
        await reserve_assertion_once(store, issuer="", assertion_id="jti", expires_at=2000)
    assert not store.seen


@pytest.mark.asyncio
async def test_database_outage_propagates_fail_closed():
    class UnavailableSession:
        async def execute(self, statement, params):
            raise OperationalError("INSERT", {}, Exception("database unavailable"))
    with pytest.raises(OperationalError):
        await reserve_assertion_once(
            UnavailableSession(), issuer="gateway", assertion_id="jti-12345678", expires_at=2000
        )
