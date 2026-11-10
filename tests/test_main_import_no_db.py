"""Smoke test that importing the real FastAPI app never opens the database.

Runs in a fresh interpreter to avoid masking import-time side effects with
modules already loaded by the rest of the pytest suite.
"""
import subprocess
import sys
from pathlib import Path


def test_main_import_does_not_initialize_database_engine():
    root = Path(__file__).resolve().parents[1]
    script = """
import sqlalchemy.ext.asyncio as sa_async

def forbid_engine(*args, **kwargs):
    raise AssertionError("app.main initialized a database engine during import")

sa_async.create_async_engine = forbid_engine
from app.main import app
assert any(route.path == "/api/v1/incidents/evidence/preview" for route in app.routes)
assert any(route.path == "/api/v1/incidents/correlation-evidence/preview" for route in app.routes)
print("main import without database engine: OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, (
        f"app.main import failed:\\nstdout: {result.stdout}\\nstderr: {result.stderr}"
    )
