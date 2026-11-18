"""Explicit opt-in replay boundary for HTTP unit tests only.

Real PostgreSQL replay and tenant E2E suites must not request this fixture.
Signature, tenant and resource authorization remain real.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def replay_unit(monkeypatch):
    import app.security as security

    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=object())
    context.__aexit__ = AsyncMock(return_value=False)
    consume = AsyncMock(return_value=True)
    monkeypatch.setattr(security, "get_session_factory", lambda: lambda: context)
    monkeypatch.setattr(security, "consume_assertion_before_access", consume)
    return consume
