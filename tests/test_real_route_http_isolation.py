"""Run the isolated real-route HTTP probe in its own process to avoid stub leakage."""
import subprocess
import sys
from pathlib import Path


def test_real_route_http_isolation():
    probe = Path(__file__).parent / "support" / "real_route_http_probe.py"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(probe)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "43 passed" in result.stdout, result.stdout
