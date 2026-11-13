"""Unit tests for the staged PostgreSQL replay helper; no database required."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.gateway_replay import (
    consume_assertion_before_access,
    reserve_assertion_once,
)


@pytest.mark.asyncio
async def test_reservation_uses_issuer_and_jti_digest_and_utc_expiry():
    result = MagicMock()
    result.scalar_one_or_none.return_value = "digest"
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    expires_at = 1_800_000_000

    reserved = await reserve_assertion_once(
        session, issuer="trusted-gateway", assertion_id="assertion-123456",
        expires_at=expires_at,
    )

    assert reserved is True
    statement, params = session.execute.await_args.args
    assert "ON CONFLICT (assertion_digest) DO NOTHING" in str(statement)
    assert len(params["digest"]) == 64
    assert params["expires_at"] == datetime.fromtimestamp(expires_at, tz=timezone.utc)


@pytest.mark.asyncio
async def test_successful_consumption_commits_before_returning_true():
    result = MagicMock()
    result.scalar_one_or_none.return_value = "digest"
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    assert await consume_assertion_before_access(
        session, issuer="trusted-gateway", assertion_id="assertion-123456",
        expires_at=1_800_000_000,
    ) is True
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_consumption_rolls_back_and_returns_false():
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    assert await consume_assertion_before_access(
        session, issuer="trusted-gateway", assertion_id="assertion-123456",
        expires_at=1_800_000_000,
    ) is False
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_and_never_grants_access():
    result = MagicMock()
    result.scalar_one_or_none.return_value = "digest"
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        commit=AsyncMock(side_effect=RuntimeError("commit failed")),
        rollback=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        await consume_assertion_before_access(
            session, issuer="trusted-gateway", assertion_id="assertion-123456",
            expires_at=1_800_000_000,
        )
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer,jti,expiry", [
    ("", "assertion-123456", 1_800_000_000),
    ("issuer", "short", 1_800_000_000),
    ("issuer", "bad" + chr(10) + "assertion", 1_800_000_000),
    ("issuer", "assertion-123456", True),
    ("issuer", "assertion-123456", 0),
])
async def test_invalid_reservation_input_fails_before_database_io(issuer, jti, expiry):
    session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())

    with pytest.raises(ValueError):
        await consume_assertion_before_access(
            session, issuer=issuer, assertion_id=jti, expires_at=expiry,
        )
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()

@pytest.mark.asyncio
async def test_database_execution_failure_rolls_back_and_propagates():
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=RuntimeError("database unavailable")),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await consume_assertion_before_access(
            session, issuer="trusted-gateway", assertion_id="assertion-123456",
            expires_at=1_800_000_000,
        )
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_same_jti_from_different_issuers_uses_distinct_replay_keys():
    import hashlib

    digests = []
    for issuer in ("gateway-a", "gateway-b"):
        result = MagicMock()
        result.scalar_one_or_none.return_value = "reserved"
        session = SimpleNamespace(execute=AsyncMock(return_value=result))
        await reserve_assertion_once(
            session, issuer=issuer, assertion_id="assertion-123456",
            expires_at=1_800_000_000,
        )
        _, params = session.execute.await_args.args
        digests.append(params["digest"])
        assert params["digest"] == hashlib.sha256(
            (issuer + "\x00" + "assertion-123456").encode()
        ).hexdigest()

    assert digests[0] != digests[1]

@pytest.mark.asyncio
async def test_successful_consumption_orders_insert_before_commit():
    events = []
    result = MagicMock()
    result.scalar_one_or_none.return_value = "reserved"

    async def execute(*args, **kwargs):
        events.append("insert")
        return result

    async def commit():
        events.append("commit")

    async def rollback():
        events.append("rollback")

    session = SimpleNamespace(
        execute=AsyncMock(side_effect=execute),
        commit=AsyncMock(side_effect=commit),
        rollback=AsyncMock(side_effect=rollback),
    )
    assert await consume_assertion_before_access(
        session, issuer="gateway", assertion_id="assertion-123456",
        expires_at=1_800_000_000,
    ) is True
    assert events == ["insert", "commit"]


@pytest.mark.asyncio
async def test_duplicate_never_commits_even_after_successful_sql_statement():
    events = []
    result = MagicMock()
    result.scalar_one_or_none.return_value = None

    async def execute(*args, **kwargs):
        events.append("insert-conflict")
        return result

    async def commit():
        events.append("commit")

    async def rollback():
        events.append("rollback")

    session = SimpleNamespace(
        execute=AsyncMock(side_effect=execute),
        commit=AsyncMock(side_effect=commit),
        rollback=AsyncMock(side_effect=rollback),
    )
    assert await consume_assertion_before_access(
        session, issuer="gateway", assertion_id="assertion-123456",
        expires_at=1_800_000_000,
    ) is False
    assert events == ["insert-conflict", "rollback"]


@pytest.mark.asyncio
async def test_same_issuer_different_jtis_produce_distinct_digests():
    digests = []
    for jti in ("assertion-123456", "assertion-123457"):
        result = MagicMock()
        result.scalar_one_or_none.return_value = "reserved"
        session = SimpleNamespace(execute=AsyncMock(return_value=result))
        assert await reserve_assertion_once(
            session, issuer="gateway", assertion_id=jti, expires_at=1_800_000_000
        )
        digests.append(session.execute.await_args.args[1]["digest"])
    assert digests[0] != digests[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("jti", [
    "a" * 129,
    "bad" + chr(0) + "assertion",
    "bad" + chr(127) + "assertion",
    "assertion-" + chr(233),
])
async def test_noncanonical_replay_jti_fails_before_sql(jti):
    session = SimpleNamespace(
        execute=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock()
    )
    with pytest.raises(ValueError, match="invalid replay reservation"):
        await consume_assertion_before_access(
            session, issuer="gateway", assertion_id=jti,
            expires_at=1_800_000_000,
        )
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()

@pytest.mark.asyncio
async def test_replay_key_does_not_change_when_expiry_changes():
    """A re-signed expiry must not create a second reservation for the same JTI."""
    digests = []
    for expiry in (1_800_000_000, 1_800_000_030):
        result = MagicMock()
        result.scalar_one_or_none.return_value = "reserved"
        session = SimpleNamespace(execute=AsyncMock(return_value=result))
        assert await reserve_assertion_once(
            session, issuer="trusted-gateway", assertion_id="assertion-123456",
            expires_at=expiry,
        )
        digests.append(session.execute.await_args.args[1]["digest"])
    assert digests[0] == digests[1]


@pytest.mark.asyncio
async def test_replay_insert_never_sends_raw_issuer_or_jti_to_database():
    result = MagicMock()
    result.scalar_one_or_none.return_value = "reserved"
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    assert await reserve_assertion_once(
        session, issuer="sensitive-issuer", assertion_id="assertion-123456",
        expires_at=1_800_000_000,
    )
    statement, params = session.execute.await_args.args
    assert set(params) == {"digest", "expires_at"}
    assert "sensitive-issuer" not in str(statement)
    assert "assertion-123456" not in str(statement)
    assert "sensitive-issuer" not in str(params)
    assert "assertion-123456" not in str(params)


@pytest.mark.asyncio
async def test_rollback_failure_does_not_return_success_on_duplicate():
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        commit=AsyncMock(),
        rollback=AsyncMock(side_effect=RuntimeError("rollback unavailable")),
    )
    with pytest.raises(RuntimeError, match="rollback unavailable"):
        await consume_assertion_before_access(
            session, issuer="gateway", assertion_id="assertion-123456",
            expires_at=1_800_000_000,
        )
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_at", ["execute", "commit"])
async def test_task_cancellation_rolls_back_and_never_returns_authorized(cancel_at):
    import asyncio

    result = MagicMock()
    result.scalar_one_or_none.return_value = "reserved"
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=asyncio.CancelledError()
            if cancel_at == "execute" else None,
            return_value=result,
        ),
        commit=AsyncMock(
            side_effect=asyncio.CancelledError()
            if cancel_at == "commit" else None,
        ),
        rollback=AsyncMock(),
    )
    with pytest.raises(asyncio.CancelledError):
        await consume_assertion_before_access(
            session, issuer="gateway", assertion_id="assertion-123456",
            expires_at=1_800_000_000,
        )
    session.rollback.assert_awaited_once()
    if cancel_at == "execute":
        session.commit.assert_not_awaited()
    else:
        session.commit.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize("issuer", [
    chr(0xD800),
    "gateway-" + chr(0xDFFF),
])
async def test_invalid_unicode_issuer_is_rejected_before_sql(issuer):
    session = SimpleNamespace(
        execute=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock()
    )
    with pytest.raises(ValueError, match="invalid replay reservation"):
        await consume_assertion_before_access(
            session, issuer=issuer, assertion_id="assertion-123456",
            expires_at=1_800_000_000,
        )
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize("expiry", [10**30, 2**63 - 1])
async def test_out_of_range_expiry_rejected_before_sql(expiry):
    session = SimpleNamespace(
        execute=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock()
    )
    with pytest.raises(ValueError, match="invalid replay reservation"):
        await consume_assertion_before_access(
            session, issuer="trusted-gateway", assertion_id="assertion-123456",
            expires_at=expiry,
        )
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize("issuer", ["g" * 1025, "gateway" + chr(0)])
async def test_unbounded_or_nul_issuer_rejected_before_sql(issuer):
    session = SimpleNamespace(
        execute=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock()
    )
    with pytest.raises(ValueError, match="invalid replay reservation"):
        await consume_assertion_before_access(
            session, issuer=issuer, assertion_id="assertion-123456",
            expires_at=1_800_000_000,
        )
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_maximum_length_issuer_remains_supported():
    result = MagicMock()
    result.scalar_one_or_none.return_value = "reserved"
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    assert await reserve_assertion_once(
        session, issuer="g" * 1024, assertion_id="assertion-123456",
        expires_at=1_800_000_000,
    ) is True
    session.execute.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize("jti", ["a" * 8, "z" * 128])
async def test_replay_jti_inclusive_length_boundaries_are_accepted(jti):
    result = MagicMock()
    result.scalar_one_or_none.return_value = "reserved"
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    assert await reserve_assertion_once(
        session, issuer="gateway", assertion_id=jti, expires_at=1_800_000_000,
    ) is True
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_minimum_positive_expiry_is_accepted_as_utc():
    result = MagicMock()
    result.scalar_one_or_none.return_value = "reserved"
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    assert await reserve_assertion_once(
        session, issuer="gateway", assertion_id="assertion-123456",
        expires_at=1,
    ) is True
    _, params = session.execute.await_args.args
    assert params["expires_at"] == datetime(1970, 1, 1, 0, 0, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_failed_commit_and_failed_rollback_cannot_return_authorized():
    result = MagicMock()
    result.scalar_one_or_none.return_value = "reserved"
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        commit=AsyncMock(side_effect=RuntimeError("commit unavailable")),
        rollback=AsyncMock(side_effect=RuntimeError("rollback unavailable")),
    )
    with pytest.raises(RuntimeError, match="rollback unavailable"):
        await consume_assertion_before_access(
            session, issuer="gateway", assertion_id="assertion-123456",
            expires_at=1_800_000_000,
        )
    session.commit.assert_awaited_once()
    session.rollback.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize("issuer,jti,expiry", [
    (None, "assertion-123456", 1_800_000_000),
    (123, "assertion-123456", 1_800_000_000),
    ("gateway", None, 1_800_000_000),
    ("gateway", b"assertion-123456", 1_800_000_000),
    ("gateway", "assertion-123456", 1_800_000_000.0),
    ("gateway", "assertion-123456", "1800000000"),
    ("gateway", "assertion-123456", -1),
])
async def test_replay_rejects_wrong_types_and_negative_expiry_before_sql(
    issuer, jti, expiry,
):
    session = SimpleNamespace(
        execute=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock()
    )
    with pytest.raises(ValueError, match="invalid replay reservation"):
        await consume_assertion_before_access(
            session, issuer=issuer, assertion_id=jti, expires_at=expiry,
        )
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
