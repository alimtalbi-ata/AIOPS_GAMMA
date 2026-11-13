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
