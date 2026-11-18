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


@pytest.mark.parametrize("endpoint,token", [
    ("https://receiver.invalid/events", "synthetic"),
    ("http://receiver.invalid/events", "synthetic"),
    ("https://receiver.invalid/events", ""),
])
def test_dispatch_hold_precedes_any_network_io(endpoint, token):
    import httpx

    requests = []

    def forbidden(request):
        requests.append(request)
        raise AssertionError("Disabled dispatch attempted network I/O")

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(forbidden), trust_env=False
        ) as client:
            with pytest.raises(RuntimeError, match="disabled"):
                await dispatch_once(client, endpoint, token)

    asyncio.run(exercise())
    assert requests == []
