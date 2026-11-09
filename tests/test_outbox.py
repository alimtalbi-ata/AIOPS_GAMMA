from datetime import timedelta

from app.outbox_relay import retry_delay, MAX_ATTEMPTS


def test_retry_delay_is_bounded():
    assert retry_delay(1) == timedelta(seconds=2)
    assert retry_delay(50) <= timedelta(seconds=300)


def test_max_attempts_is_finite():
    assert 1 <= MAX_ATTEMPTS <= 20
