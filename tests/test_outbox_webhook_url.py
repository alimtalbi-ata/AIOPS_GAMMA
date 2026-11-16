"""Pure unit regression for the outbox relay's fail-closed destination validation."""

import pytest

from app.outbox_relay import valid_webhook_endpoint


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
    ],
)
def test_rejects_unsafe_or_malformed_webhook(endpoint):
    assert not valid_webhook_endpoint(endpoint)
