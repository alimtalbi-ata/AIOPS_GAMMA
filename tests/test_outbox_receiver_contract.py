"""Offline receiver contract tests. No network or production database."""
from uuid import uuid4

import httpx
import pytest


class SyntheticReceiver:
    def __init__(self):
        self.effects = {}
        self.fail_next = False
        self.lose_ack = False

    def __call__(self, request):
        import json
        body = json.loads(request.content)
        key = (body["tenant_id"], request.headers["X-Event-Id"])
        if body["event_id"] != key[1]:
            return httpx.Response(400)
        if self.fail_next:
            self.fail_next = False
            return httpx.Response(503, headers={"Retry-After": "2"})
        if key in self.effects and self.effects[key] != body:
            return httpx.Response(409)
        self.effects[key] = body
        if self.lose_ack:
            self.lose_ack = False
            raise httpx.ReadTimeout("synthetic lost acknowledgement", request=request)
        return httpx.Response(200)


@pytest.mark.asyncio
async def test_synthetic_receiver_retry_and_duplicate_contract():
    receiver = SyntheticReceiver()
    event = str(uuid4())
    body = {"tenant_id": str(uuid4()), "event_id": event, "payload": {"test": True}}
    headers = {"X-Event-Id": event}
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver),
                                 trust_env=False) as client:
        receiver.fail_next = True
        response = await client.post("https://receiver.invalid/events", json=body, headers=headers)
        assert response.status_code == 503
        assert not receiver.effects
        for _ in range(2):
            response = await client.post("https://receiver.invalid/events", json=body, headers=headers)
            assert response.status_code == 200
        assert len(receiver.effects) == 1
        response = await client.post("https://receiver.invalid/events",
                                     json={**body, "payload": {"changed": True}}, headers=headers)
        assert response.status_code == 409
        assert len(receiver.effects) == 1
        response = await client.post("https://receiver.invalid/events",
                                     json={**body, "tenant_id": str(uuid4())}, headers=headers)
        assert response.status_code == 200
        assert len(receiver.effects) == 2


@pytest.mark.asyncio
async def test_lost_acknowledgement_replays_without_duplicate_effect():
    receiver = SyntheticReceiver()
    receiver.lose_ack = True
    event = str(uuid4())
    body = {"tenant_id": str(uuid4()), "event_id": event, "payload": {"test": True}}
    headers = {"X-Event-Id": event}
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver),
                                 trust_env=False) as client:
        with pytest.raises(httpx.ReadTimeout):
            await client.post("https://receiver.invalid/events", json=body, headers=headers)
        assert len(receiver.effects) == 1
        response = await client.post("https://receiver.invalid/events", json=body, headers=headers)
        assert response.status_code == 200
        assert len(receiver.effects) == 1


def test_retry_budget_contract():
    from app.outbox_relay import MAX_ATTEMPTS, retry_delay, permanent_receiver_rejection
    assert MAX_ATTEMPTS == 10
    assert all(0 < retry_delay(n).total_seconds() <= 300 for n in range(1, 11))
    request = httpx.Request("POST", "https://receiver.invalid/events")
    for status in (400, 409, 503, 429, 408, 425):
        response = httpx.Response(status, request=request)
        error = httpx.HTTPStatusError("synthetic", request=request, response=response)
        assert permanent_receiver_rejection(error) == (status in (400, 409))
