"""Pure unit regression for the outbox relay's fail-closed destination validation."""

import asyncio

import pytest

from app.outbox_relay import dispatch_once, valid_webhook_endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://receiver.example.test/events",
        "https://receiver.example.test:8443/events",
    ],
)
def test_accepts_plain_https_webhook(endpoint):
    assert valid_webhook_endpoint(endpoint)


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "https://",
        "http://receiver.example.test/events",
        "https://user:pass@receiver.example.test/events",
        "https://receiver.example.test/events?token=secret",
        "https://receiver.example.test/events#fragment",
        "https://receiver.example.test:invalid/events",
        "https://receiver.example.test:99999/events",
        "https://receiver.example.test:0/events",
        " https://receiver.example.test/events",
        "https://receiver.example.test/events ",
        "https://receiver.example.test/events\n",
    ],
)
def test_rejects_unsafe_or_malformed_webhook(endpoint):
    assert not valid_webhook_endpoint(endpoint)


def test_dispatch_rejects_invalid_destination_before_touching_database(monkeypatch):
    def must_not_access_database():
        raise AssertionError("Unsafe endpoint reached the database")

    monkeypatch.setattr("app.outbox_relay.get_session_factory", must_not_access_database)
    for endpoint, token in (
        ("http://receiver.example.test/events", "secret"),
        ("https://receiver.example.test:99999/events", "secret"),
        ("https://receiver.example.test/events", ""),
        (" https://receiver.example.test/events", "secret"),
    ):
        with pytest.raises(ValueError, match="Invalid HTTPS outbox receiver"):
            asyncio.run(dispatch_once(None, endpoint, token))
