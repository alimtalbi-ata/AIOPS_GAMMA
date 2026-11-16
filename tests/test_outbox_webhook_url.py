"""Pure unit regression for the outbox relay's fail-closed destination validation."""

import asyncio
from datetime import timedelta

import pytest

from app.outbox_relay import dispatch_once, retry_delay, valid_webhook_endpoint, valid_webhook_token


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
        "HTTPS://receiver.example.test/events",
        "Https://receiver.example.test/events",
        "https:receiver.example.test/events",
        "https://user:pass@receiver.example.test/events",
        "https://@receiver.example.test/events",
        "https://user@receiver.example.test/events",
        "https://:pass@receiver.example.test/events",
        "https://receiver.example.test/events?token=secret",
        "https://receiver.example.test/events?",
        "https://receiver.example.test/events#",
        "https://receiver.example.test/events?#",
        "https://receiver.example.test/events#fragment",
        "https://receiver.example.test:invalid/events",
        "https://receiver.example.test:99999/events",
        "https://receiver.example.test:0/events",
        " https://receiver.example.test/events",
        "https://receiver.example.test/events ",
        "https://receiver.example.test/events\n",
        "https://receiver.example.test/ev\nents",
        "https://receiver.example.test/ev\tents",
        "https://receiver.example.test/ev\x00ents",
        "https://receiver.example.test/ev\x7fents",
        "https://receiver.example.test/ev ents",
        "https://receiver.example.test/café",
        "https://receiver.example.test/ev\u2028ents",
        "https://receiver.example.test/ev\u00a0ents",
        "https://receiver.example.test\\@untrusted.example.test/events",
    ],
)
def test_rejects_unsafe_or_malformed_webhook(endpoint):
    assert not valid_webhook_endpoint(endpoint)


@pytest.mark.parametrize("token", ["secret", "token-with-._~+/="])
def test_accepts_nonempty_bearer_token(token):
    assert valid_webhook_token(token)


@pytest.mark.parametrize("token", ["", " ", " secret", "secret ", "secret\n", "sec\tret", "sec\x00ret", "sec\x7fret", "sec\x80ret", "tökén", "sec ret", "secret:other", "secret,other", "secret;other", "secret=other", "secret!", None])
def test_rejects_malformed_bearer_token(token):
    assert not valid_webhook_token(token)


def test_dispatch_rejects_invalid_destination_before_touching_database(monkeypatch):
    def must_not_access_database():
        raise AssertionError("Unsafe endpoint reached the database")

    monkeypatch.setattr("app.outbox_relay.get_session_factory", must_not_access_database)
    for endpoint, token in (
        ("http://receiver.example.test/events", "secret"),
        ("HTTPS://receiver.example.test/events", "secret"),
        ("https://receiver.example.test:99999/events", "secret"),
        ("https://receiver.example.test/events?", "secret"),
        ("https://receiver.example.test/events#", "secret"),
        ("https://receiver.example.test/events", ""),
        ("https://receiver.example.test/events", " "),
        ("https://receiver.example.test/events", "secret\n"),
        ("https://receiver.example.test/events", "sec\x00ret"),
        ("https://receiver.example.test/events", "sec\tret"),
        ("https://receiver.example.test/events", "sec\x7fret"),
        ("https://receiver.example.test/events", "tökén"),
        ("https://receiver.example.test/events", "sec ret"),
        ("https://receiver.example.test/events", "secret:other"),
        ("https://receiver.example.test/events", "secret=other"),
        ("https://@receiver.example.test/events", "secret"),
        (" https://receiver.example.test/events", "secret"),
        ("https://receiver.example.test/ev\nents", "secret"),
        ("https://receiver.example.test/café", "secret"),
        ("https://receiver.example.test/ev ents", "secret"),
        ("https://receiver.example.test\\@untrusted.example.test/events", "secret"),
    ):
        with pytest.raises(ValueError, match="Invalid HTTPS outbox receiver"):
            asyncio.run(dispatch_once(None, endpoint, token))


@pytest.mark.parametrize(
    ("attempts", "seconds"),
    [(1, 2), (2, 4), (3, 8), (7, 128), (8, 256), (9, 300), (10, 300), (100, 300)],
)
def test_retry_backoff_is_bounded(attempts, seconds):
    assert retry_delay(attempts) == timedelta(seconds=seconds)
