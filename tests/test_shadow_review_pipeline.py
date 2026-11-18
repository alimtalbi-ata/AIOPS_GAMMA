from datetime import datetime, timezone, timedelta
import pytest
from app.reused.shadow_review_integrity import seal_review
from app.reused.shadow_review_auth import sign_synthetic_review
from app.reused.shadow_review_pipeline import receive_review


@pytest.mark.parametrize("attack", ["actor", "tenant", "key", "expired", "tamper", "blocked"])
def test_invalid_review_does_not_consume(tmp_path, attack):
    now = datetime.now(timezone.utc)
    report = {"tenant_id": "a", "authoritative": False, "live_execution_authorized": False,
              "approval_state": "NOT_GRANTED", "human_review_required": True,
              "execution_state": "NOT_EXECUTED",
              "review_state": "BLOCKED" if attack == "blocked" else "REVIEW_CANDIDATE"}
    envelope = seal_review(report, now)
    key = b"x"*32
    signed = sign_synthetic_review(envelope, now, envelope["sha256"], "actor", "a", "v1", key)
    path = tmp_path / "registry.sqlite"
    if attack == "tamper":
        envelope["body"]["report"]["extra"] = True
    with pytest.raises(ValueError):
        receive_review(path, envelope, now + timedelta(seconds=300 if attack == "expired" else 0),
                       signed, "other" if attack == "actor" else "actor",
                       "b" if attack == "tenant" else "a", {} if attack == "key" else {"v1": key})
    assert not path.exists()


def test_valid_review_is_consumed_once(tmp_path):
    now = datetime.now(timezone.utc)
    envelope = seal_review({"tenant_id": "a", "authoritative": False,
        "live_execution_authorized": False, "approval_state": "NOT_GRANTED",
        "human_review_required": True, "execution_state": "NOT_EXECUTED",
        "review_state": "REVIEW_CANDIDATE"}, now)
    key = b"x"*32
    signed = sign_synthetic_review(envelope, now, envelope["sha256"], "actor", "a", "v1", key)
    args = (tmp_path / "registry.sqlite", envelope, now, signed, "actor", "a", {"v1": key})
    assert receive_review(*args)["state"] == "SYNTHETIC_CONSUMED"
    result = receive_review(*args)
    assert result["state"] == "REPLAY_REJECTED"
    assert result["live_execution_authorized"] is False
