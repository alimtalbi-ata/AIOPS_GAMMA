from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest
from app.reused.shadow_review_integrity import seal_review
from app.reused.shadow_review_replay import consume_synthetic_review


def test_concurrent_consumption_and_persistence(tmp_path):
    now = datetime.now(timezone.utc)
    envelope = seal_review({"tenant_id": "a", "authoritative": False,
                            "approval_state": "NOT_GRANTED", "live_execution_authorized": False}, now)
    path = tmp_path / "replay.sqlite"
    def consume():
        return consume_synthetic_review(path, envelope, now, envelope["sha256"], "a")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert sorted(r["state"] for r in results) == ["REPLAY_REJECTED", "SYNTHETIC_CONSUMED"]
    assert all(r["live_execution_authorized"] is False for r in results)
    assert consume()["state"] == "REPLAY_REJECTED"
    with pytest.raises(ValueError, match="Tenant mismatch"):
        consume_synthetic_review(path, envelope, now, envelope["sha256"], "b")
