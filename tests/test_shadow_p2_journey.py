"""End-to-end synthetic dossier qualification; no network or live credentials."""
from test_shadow_inbox_rca import inputs
from test_shadow_remediation_preview import candidate
from app.reused.shadow_review_dossier import build_review_dossier
from app.reused.shadow_remediation_risk import SyntheticRiskInput
from app.reused.shadow_review_integrity import seal_review
from app.reused.shadow_review_auth import sign_synthetic_review
from app.reused.shadow_review_pipeline import receive_review


def test_full_shadow_journey(tmp_path):
    receipt, investigation = inputs()
    now = investigation.as_of
    report = build_review_dossier(receipt, investigation, "payment", (), "timeout",
                                  (candidate(),), SyntheticRiskInput("low", 1, True, True, True))
    assert report["review_state"] == "REVIEW_CANDIDATE"
    envelope = seal_review(report, now)
    key = b"s" * 32
    signed = sign_synthetic_review(envelope, now, envelope["sha256"], "reviewer", receipt.tenant_id, "test", key)
    args = (tmp_path / "synthetic.sqlite", envelope, now, signed, "reviewer", receipt.tenant_id, {"test": key})
    first = receive_review(*args)
    assert first["state"] == "SYNTHETIC_CONSUMED"
    assert first["approval_state"] == "NOT_GRANTED"
    assert first["execution_state"] == "NOT_EXECUTED"
    assert first["live_execution_authorized"] is False
    assert receive_review(*args)["state"] == "REPLAY_REJECTED"
