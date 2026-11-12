"""Unit-level runner contract: mocked pytest, no application or network execution."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import run_bounded_lab as lab


@pytest.fixture
def simulated_runner(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    for filename in lab.REQUIRED_FILES:
        target = root / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("placeholder\n", encoding="utf-8")
    monkeypatch.setattr(lab, "__file__", str(root / "scripts" / "run_bounded_lab.py"))
    for key in lab.UNSAFE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return root


@pytest.mark.parametrize("code,expected", [(0, "pass"), (1, "fail"), (2, "fail")])
def test_report_and_exit_code_are_faithful(simulated_runner, tmp_path, monkeypatch, capsys, code, expected):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=code)

    monkeypatch.setattr(lab.subprocess, "run", fake_run)
    report_path = tmp_path / "result.json"
    monkeypatch.setattr(sys, "argv", ["runner", "--report", str(report_path)])
    assert lab.main() == code
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == [sys.executable, "-m", "pytest", "-q", *lab.SAFE_TESTS]
    assert kwargs["cwd"] == simulated_runner
    assert kwargs["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert kwargs["check"] is False
    result = json.loads(report_path.read_text())
    assert result["exit_code"] == code
    assert result["result"] == expected
    assert result["tests"] == list(lab.SAFE_TESTS)
    assert json.loads(capsys.readouterr().out) == result


def test_unsafe_report_is_rejected_before_pytest(simulated_runner, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("pytest must not start")

    monkeypatch.setattr(lab.subprocess, "run", forbidden)
    monkeypatch.setattr(sys, "argv", ["runner", "--report", str(simulated_runner / "report.json")])
    assert lab.main() == 2


def test_db_guard_is_checked_before_pytest(simulated_runner, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("pytest must not start")

    monkeypatch.setattr(lab.subprocess, "run", forbidden)
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setattr(sys, "argv", ["runner"])
    assert lab.main() == 2
