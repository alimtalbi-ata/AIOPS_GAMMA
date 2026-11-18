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
assert any(route.path == "/api/v1/incidents/correlation/preview" for route in app.routes)
assert any(route.path == "/api/v1/health/live" for route in app.routes)
assert any(route.path == "/api/v1/policy/remediation/preview" for route in app.routes)
print("main import without database engine: OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, (
        f"app.main import failed:\\nstdout: {result.stdout}\\nstderr: {result.stderr}"
    )


def test_health_and_preview_routes_do_not_create_database_engine():
    """Exercise actual FastAPI handlers while engine creation is forbidden."""
    root = Path(__file__).resolve().parents[1]
    script = """
import os
os.environ["INTERNAL_API_KEY"] = "isolated-test-key"
import sqlalchemy.ext.asyncio as sa_async

def forbid_engine(*args, **kwargs):
    raise AssertionError("read-only HTTP route initialized a database engine")

sa_async.create_async_engine = forbid_engine
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.settings import settings
import base64, hashlib, hmac, json, time
from uuid import uuid4
settings.gateway_assertion_secret = "s" * 48
settings.gateway_assertion_issuer = "test-gateway"
settings.gateway_assertion_audience = "gamma-api"
settings.gateway_assertion_keys = {}
settings.gateway_assertion_max_ttl_seconds = 60

# Keep the actual authentication dependency, HMAC checks and transaction
# helper. Only substitute the database session at the replay boundary.
from unittest.mock import AsyncMock, MagicMock
import app.security as security
import app.db as db
replay = AsyncMock()
replay.execute.return_value = MagicMock(scalar_one_or_none=lambda: "reserved")
replay_context = MagicMock()
replay_context.__aenter__ = AsyncMock(return_value=replay)
replay_context.__aexit__ = AsyncMock(return_value=False)
security.get_session_factory = lambda: lambda: replay_context
db.get_session_factory = forbid_engine

def signed_headers(path):
    now = int(time.time())
    claims = {"iss": "test-gateway", "aud": "gamma-api", "sub": "user:smoke",
              "actor_type": "user", "tenant_id": "11111111-1111-4111-8111-111111111111",
              "tenant_access": True, "iat": now, "exp": now + 30,
              "jti": uuid4().hex, "method": "POST", "path": path}
    raw = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(hmac.new(b"s" * 48, raw, hashlib.sha256).digest()).rstrip(b"=")
    return {"X-Internal-API-Key": "isolated-test-key", "X-Gateway-Principal": (raw + b"." + sig).decode()}

headers = {
    "X-Internal-API-Key": "isolated-test-key",
    "X-Tenant-ID": "11111111-1111-4111-8111-111111111111",
}
signal = {
    "source": "otel", "external_event_id": "evt-1",
    "service_name": "checkout", "environment": "prod",
    "severity": "major", "status": "firing",
    "observed_at": datetime.now(timezone.utc).isoformat(),
    "symptom_key": "latency",
}
with TestClient(app) as client:
    health = client.get("/api/v1/health/live")
    assert health.status_code == 200, health.text
    correlation = client.post(
        "/api/v1/incidents/correlation/preview",
        json={"signals": [signal]}, headers=signed_headers("/api/v1/incidents/correlation/preview"),
    )
    assert correlation.status_code == 200, correlation.text
    assert correlation.headers["cache-control"] == "no-store"
    joined = client.post(
        "/api/v1/incidents/correlation-evidence/preview",
        json={"correlation": {"signals": [signal]}, "evidence": []},
        headers=signed_headers("/api/v1/incidents/correlation-evidence/preview"),
    )
    assert joined.status_code == 200, joined.text
    assert joined.json()["evidence_join_complete"] is False
assert replay.execute.await_count == 2
assert replay.commit.await_count == 2
assert replay.rollback.await_count == 0
assert replay_context.__aenter__.await_count == 2
print("real HTTP preview routes with synthetic replay transaction and without DB engine: OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, (
        f"Real FastAPI preview smoke test failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
