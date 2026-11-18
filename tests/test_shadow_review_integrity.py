from datetime import datetime, timezone, timedelta
import pytest
from app.reused.shadow_review_integrity import seal_review, check_review


def test_integrity_and_expiration():
    now = datetime.now(timezone.utc)
    report = {"authoritative": False, "live_execution_authorized": False,
              "approval_state": "NOT_GRANTED"}
    envelope = seal_review(report, now)
    digest = envelope["sha256"]
    assert check_review(envelope, now, digest)["live_execution_authorized"] is False
    with pytest.raises(ValueError, match="validity"):
        check_review(envelope, now + timedelta(seconds=300), digest)
    envelope["body"]["report"]["approval_state"] = "GRANTED"
    with pytest.raises(ValueError, match="Digest"):
        check_review(envelope, now, digest)
