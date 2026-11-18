"""Local synthetic replay registry. Never consumes real approvals."""
import sqlite3
from app.reused.shadow_review_integrity import check_review


def consume_synthetic_review(path, envelope, now, expected_digest, tenant_id):
    checked = check_review(envelope, now, expected_digest)
    if type(tenant_id) is not str or not tenant_id.strip():
        raise ValueError("Missing tenant")
    if envelope["body"]["report"].get("tenant_id") != tenant_id:
        raise ValueError("Tenant mismatch")
    conn = sqlite3.connect(path, timeout=5)
    try:
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS synthetic_review_receipts (tenant TEXT NOT NULL, dossier TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY (tenant,dossier))")
            cursor = conn.execute("INSERT INTO synthetic_review_receipts VALUES (?,?,?) ON CONFLICT(tenant,dossier) DO NOTHING",
                                  (tenant_id, checked["id"], expected_digest))
            accepted = cursor.rowcount == 1
        return {"state": "SYNTHETIC_CONSUMED" if accepted else "REPLAY_REJECTED",
                "approval_state": "NOT_GRANTED", "live_execution_authorized": False}
    finally:
        conn.close()
