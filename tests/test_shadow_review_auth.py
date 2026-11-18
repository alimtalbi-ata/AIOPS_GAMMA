from datetime import datetime, timezone
import pytest
from app.reused.shadow_review_integrity import seal_review
from app.reused.shadow_review_auth import sign_synthetic_review, verify_synthetic_review


def test_binding_and_key_retirement():
    now = datetime.now(timezone.utc)
    envelope = seal_review({"tenant_id": "a", "authoritative": False,
                            "approval_state": "NOT_GRANTED", "live_execution_authorized": False}, now)
    key = b"x" * 32
    signed = sign_synthetic_review(envelope, now, envelope["sha256"], "actor-a", "a", "v1", key)
    def verify(keys, actor="actor-a", tenant="a"):
        return verify_synthetic_review(envelope, now, signed, actor, tenant, keys)
    assert verify({"v1": key, "v2": b"y"*32})["live_execution_authorized"] is False
    with pytest.raises(ValueError, match="retired"):
        verify({"v2": b"y"*32})
    with pytest.raises(ValueError, match="Identity"):
        verify({"v1": key}, tenant="b")
    with pytest.raises(ValueError, match="Identity"):
        verify({"v1": key}, actor="actor-b")
    with pytest.raises(ValueError, match="MAC"):
        verify({"v1": b"z"*32})
    signed["claims"]["actor"] = "actor-b"
    with pytest.raises(ValueError, match="MAC"):
        verify({"v1": key}, actor="actor-b")
