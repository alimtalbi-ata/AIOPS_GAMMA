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
    for key in (*lab.UNSAFE_ENV_KEYS, "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH"):
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
    assert cmd == [sys.executable, "-m", "pytest", "-q", "-p", "pytest_asyncio.plugin", *lab.SAFE_TESTS]
    assert kwargs["cwd"] == simulated_runner
    assert kwargs["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert kwargs["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert kwargs["check"] is False
    assert kwargs["timeout"] == lab.LAB_TIMEOUT_SECONDS
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


def test_dotenv_guard_runs_before_pytest(simulated_runner, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("pytest must not start")

    monkeypatch.setattr(lab.subprocess, "run", forbidden)
    (simulated_runner / ".env").write_text("DATABASE_URL=unsafe\\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["runner"])
    assert lab.main() == 2


def test_pytest_timeout_is_reported_as_failure(simulated_runner, tmp_path, monkeypatch, capsys):
    def expired(cmd, **kwargs):
        raise lab.subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(lab.subprocess, "run", expired)
    report_path = tmp_path / "timeout.json"
    monkeypatch.setattr(sys, "argv", ["runner", "--report", str(report_path)])
    assert lab.main() == 124
    report = json.loads(report_path.read_text())
    assert report["result"] == "timeout"
    assert report["exit_code"] == 124
    assert report["timeout_seconds"] == lab.LAB_TIMEOUT_SECONDS
    assert json.loads(capsys.readouterr().out) == report
