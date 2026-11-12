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
    from app.main import app
    import app.db

    def forbidden():
        raise AssertionError("demo must never access DB")
    monkeypatch.setattr(app.db, "get_session_factory", forbidden)
    with TestClient(app) as client:
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
