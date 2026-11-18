import asyncio
from unittest.mock import AsyncMock
import pytest
from app.outbox_relay import dispatch_once, main, _unqualified_relay_main


def test_all_relay_entrypoints_fail_closed():
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="disabled"):
        asyncio.run(dispatch_once(client, "https://receiver.example/", "synthetic"))
    client.post.assert_not_called()
    for entrypoint in (main, _unqualified_relay_main):
        with pytest.raises(RuntimeError, match="disabled"):
            asyncio.run(entrypoint())
