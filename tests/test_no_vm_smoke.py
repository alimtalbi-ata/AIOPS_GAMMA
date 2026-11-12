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
