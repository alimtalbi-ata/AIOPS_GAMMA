"""No-network tests for the bounded lab runner preflight.

Only invokes --check-only on a disposable synthetic checkout: never pytest,
PostgreSQL, Docker, GitHub runners, staging services or LIVE resources.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import run_bounded_lab


@pytest.fixture
def fake_checkout(tmp_path):
    root = tmp_path / "synthetic-gamma"
    runner = root / "scripts" / "run_bounded_lab.py"
    runner.parent.mkdir(parents=True)
    shutil.copyfile(Path(run_bounded_lab.__file__), runner)
    for name in run_bounded_lab.REQUIRED_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# placeholder, not repository source\n", encoding="utf-8")
    return root, runner


def invoke(runner, *args, env=None):
    clean = os.environ.copy()
    for key in run_bounded_lab.UNSAFE_ENV_KEYS:
        clean.pop(key, None)
    if env:
        clean.update(env)
    return subprocess.run(
        [sys.executable, str(runner), "--check-only", *map(str, args)],
        capture_output=True, text=True, env=clean, check=False,
    )


def test_preflight_accepts_complete_synthetic_checkout_without_executing_pytest(fake_checkout):
    _, runner = fake_checkout
    result = invoke(runner)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["note"] == "No pytest tests executed"
    assert "tests/test_gateway_replay_postgres.py" not in payload["test_files"]
    assert len(payload["test_files"]) == len(run_bounded_lab.SAFE_TESTS)


def test_preflight_rejects_incomplete_checkout(fake_checkout):
    root, runner = fake_checkout
    (root / "app" / "security.py").unlink()
    result = invoke(runner)
    assert result.returncode == 2
    assert "Refusing incomplete checkout" in result.stderr


@pytest.mark.parametrize("key", run_bounded_lab.UNSAFE_ENV_KEYS)
def test_preflight_rejects_inherited_db_variables_even_empty(fake_checkout, key):
    _, runner = fake_checkout
    result = invoke(runner, env={key: ""})
    assert result.returncode == 2
    assert "database/replay" in result.stderr


@pytest.mark.parametrize("target", [
    "lab-report.json",
    "tests/../lab-report.json",
])
def test_preflight_rejects_report_inside_checkout(fake_checkout, target):
    root, runner = fake_checkout
    result = invoke(runner, "--report", root / target)
    assert result.returncode == 2
    assert "outside repository checkout" in result.stderr
    assert not (root / "lab-report.json").exists()


def test_preflight_accepts_report_outside_checkout_without_creating_it(fake_checkout, tmp_path):
    _, runner = fake_checkout
    report = tmp_path / "report.json"
    result = invoke(runner, "--report", report)
    assert result.returncode == 0
    assert not report.exists()
