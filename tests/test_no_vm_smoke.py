"""No-VM smoke tests against actual FastAPI app, no external services."""
from scripts import smoke_no_vm
from app.settings import settings


def test_no_vm_smoke_checks_actual_app_without_external_services(monkeypatch, capsys):
    monkeypatch.setattr(settings, "internal_api_key", "")
    monkeypatch.setattr(settings, "gateway_assertion_secret", "")
    assert smoke_no_vm.main() == 0
    assert "PASS no-VM API smoke" in capsys.readouterr().out


def test_no_vm_smoke_refuses_real_credentials(monkeypatch, capsys):
    monkeypatch.setattr(settings, "internal_api_key", "configured-secret")
    assert smoke_no_vm.main() == 2
    assert "refusing smoke" in capsys.readouterr().err


def test_synthetic_correlation_http_is_real_engine_and_has_no_db(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app as gamma_app
    import app.db as gamma_db

    def forbidden():
        raise AssertionError("demo must never access DB")
    monkeypatch.setattr(gamma_db, "get_session_factory", forbidden)
    with TestClient(gamma_app) as client:
        response = client.get("/api/v1/demo/correlation")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.json()
    assert payload["mode"] == "synthetic_demo"
    assert payload["authoritative"] is False
    assert payload["correlation"]["source_events"] == 2
    assert len(payload["correlation"]["groups"]) == 1
    assert payload["correlation"]["persisted"] is False
    assert payload["correlation"]["live_remediation_authorized"] is False


def test_synthetic_investigation_http_joins_evidence_without_db(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app as gamma_app
    import app.db as gamma_db

    def forbidden():
        raise AssertionError("demo must never access DB")
    monkeypatch.setattr(gamma_db, "get_session_factory", forbidden)
    with TestClient(gamma_app) as client:
        response = client.get("/api/v1/demo/investigation")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.json()
    assert payload["mode"] == "synthetic_demo"
    assert payload["authoritative"] is False
    assert payload["evidence_source_verified"] is False
    investigation = payload["investigation"]
    assert investigation["source_events"] == 2
    assert investigation["evidence_join_complete"] is True
    assert investigation["evidence_join_consistent"] is True
    assert len(investigation["groups"]) == 1
    group = investigation["groups"][0]
    assert group["evidence_covered_events"] == 2
    assert group["evidence_missing_events"] == 0
    assert group["evidence_state"] == "UNVERIFIED"
    assert len(group["evidence"]) == 2
    assert investigation["persisted"] is False
    assert investigation["live_remediation_authorized"] is False
