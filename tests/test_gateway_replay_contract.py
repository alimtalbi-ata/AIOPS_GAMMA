"""Unit contract tests for proposed shared replay store, not live DB."""
import pytest
from sqlalchemy.exc import OperationalError

from app.gateway_replay import reserve_assertion_once, consume_assertion_before_access


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


class TransactionalFakeSession(FakeSession):
    def __init__(self, fail_commit=False):
        super().__init__()
        self.commits = 0
        self.rollbacks = 0
        self.fail_commit = fail_commit

    async def commit(self):
        if self.fail_commit:
            raise OperationalError("COMMIT", {}, Exception("commit unavailable"))
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_replay_is_committed_before_access_and_duplicate_is_denied():
    store = TransactionalFakeSession()
    assert await consume_assertion_before_access(
        store, issuer="gateway", assertion_id="jti-12345678", expires_at=2000
    )
    assert store.commits == 1
    assert not await consume_assertion_before_access(
        store, issuer="gateway", assertion_id="jti-12345678", expires_at=2000
    )
    assert store.commits == 1
    assert store.rollbacks == 1


@pytest.mark.asyncio
async def test_failed_commit_never_grants_access():
    store = TransactionalFakeSession(fail_commit=True)
    with pytest.raises(OperationalError):
        await consume_assertion_before_access(
            store, issuer="gateway", assertion_id="jti-12345678", expires_at=2000
        )
    assert store.commits == 0
    assert store.rollbacks == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer,jti,expiry", [
    (None, "valid-jti", 2000), (123, "valid-jti", 2000),
    ("gateway", None, 2000), ("gateway", 42, 2000),
    ("gateway", "valid-jti", True), ("gateway", "valid-jti", 30.5),
    ("gateway", "valid-jti", "2000"), ("gateway", "valid-jti", 0),
])
async def test_invalid_replay_inputs_do_not_touch_database(issuer, jti, expiry):
    store = FakeSession()
    with pytest.raises(ValueError):
        await reserve_assertion_once(store, issuer=issuer, assertion_id=jti, expires_at=expiry)
    assert not store.digests


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer,jti", [
    ("gateway" + chr(0) + "alternate", "valid-jti"),
    ("gateway", "short"),
    ("gateway", "        "),
    ("gateway", "jti-abc\\n123"),
    ("gateway", "é" * 8),
    ("gateway", "x" * 129),
])
async def test_ambiguous_or_noncanonical_replay_keys_never_reach_database(issuer, jti):
    store = FakeSession()
    with pytest.raises(ValueError):
        await reserve_assertion_once(
            store, issuer=issuer, assertion_id=jti, expires_at=2000
        )
    assert not store.digests
