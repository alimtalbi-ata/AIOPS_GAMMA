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
    with pytest.raises(ValueError, match="Digest|unapproved"):
        check_review(envelope, now, digest)


@pytest.mark.parametrize("mutation", ["id", "approval", "authority", "live", "extra", "timestamp"])
def test_recomputed_digest_cannot_bypass_schema(mutation):
    from app.reused.shadow_review_integrity import _digest
    now = datetime.now(timezone.utc)
    envelope = seal_review({"authoritative": False, "live_execution_authorized": False,
                            "approval_state": "NOT_GRANTED"}, now)
    body = envelope["body"]
    if mutation == "id":
        body["id"] = "not-a-uuid"
    elif mutation == "approval":
        body["report"]["approval_state"] = "GRANTED"
    elif mutation == "authority":
        body["report"]["authoritative"] = True
    elif mutation == "live":
        body["report"]["live_execution_authorized"] = True
    elif mutation == "extra":
        body["unexpected"] = True
    else:
        body["issued_at"] = 123
    envelope["sha256"] = _digest(body)
    with pytest.raises(ValueError):
        check_review(envelope, now, envelope["sha256"])
