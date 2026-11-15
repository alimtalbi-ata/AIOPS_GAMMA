"""Real HTTP tenant-isolation tests against an explicitly disposable PostgreSQL DB.

Requires the reviewed Alembic head (0002_gateway_replay) on a loopback-only
database named *_tenant_test. Never use staging or production credentials.

    GAMMA_TENANT_TEST_ALLOW_WRITE=I_UNDERSTAND_DISPOSABLE_DB \
    GAMMA_TENANT_TEST_DATABASE_URL=postgresql+asyncpg://...@localhost/gamma_tenant_test \
      python -m pytest -q tests/test_resource_list_http_postgres.py
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from ipaddress import ip_address
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import get_session
from app.main import app
from app.models import Evidence, ServiceBinding
from app.settings import settings


TENANT_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
TENANT_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
INCIDENT = "gamma-tenant-postgres-shared-incident"


def _require_disposable_url(raw_url: str) -> str:
    if not raw_url:
        pytest.skip("No explicitly disposable tenant PostgreSQL URL configured")
    parsed = make_url(raw_url)
    # URL query keys such as ?host= can override the apparent loopback host.
    if parsed.query:
        pytest.fail("Tenant integration refuses connection URL query overrides")
    if parsed.drivername != "postgresql+asyncpg":
        pytest.fail("Tenant integration requires postgresql+asyncpg")
    if not parsed.database or not parsed.database.endswith("_tenant_test"):
        pytest.fail("Tenant integration requires a database named *_tenant_test")
    if parsed.host not in ("localhost", "127.0.0.1", "::1"):
        pytest.fail("Tenant integration requires loopback PostgreSQL only")
    return raw_url


@pytest.fixture
def tenant_postgres():
    url = _require_disposable_url(os.environ.get("GAMMA_TENANT_TEST_DATABASE_URL", ""))
    if os.environ.get("GAMMA_TENANT_TEST_ALLOW_WRITE") != "I_UNDERSTAND_DISPOSABLE_DB":
        pytest.fail("Explicit disposable database write acknowledgement required")

    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    binding_ids = [uuid4(), uuid4()]
    evidence_ids = [uuid4(), uuid4(), uuid4()]
    investigation_ids = [uuid4(), uuid4(), uuid4()]

    async def prepare():
        async with engine.connect() as connection:
            db_name = await connection.scalar(text("SELECT current_database()"))
            if not db_name or not db_name.endswith("_tenant_test"):
                pytest.fail("Unsafe connected database")
            server_address = await connection.scalar(text("SELECT inet_server_addr()"))
            if server_address is None or not ip_address(str(server_address)).is_loopback:
                pytest.fail("Connected PostgreSQL server is not loopback TCP")
            superuser = await connection.scalar(text(
                "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
            ))
            if superuser is not False:
                pytest.fail("Disposable tenant test refuses PostgreSQL superuser")
            version = await connection.scalar(text("SHOW server_version_num"))
            if not 160000 <= int(version) < 170000:
                pytest.fail("Disposable tenant test requires PostgreSQL 16")
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != "0002_gateway_replay":
                pytest.fail("Disposable tenant database must be at reviewed Alembic head 0002")
            for table in ("telemetry_service_bindings", "investigation_evidence"):
                present = await connection.scalar(text("SELECT to_regclass(:name)"), {"name": table})
                if present is None:
                    pytest.fail(f"Required migrated table missing: {table}")
                count = await connection.scalar(text(f"SELECT count(*) FROM {table}"))
                if count != 0:
                    pytest.fail(f"Disposable database must start empty; {table} contains {count} rows")

        async with factory() as session:
            session.add_all([
                ServiceBinding(
                    id=binding_ids[0], tenant_id=TENANT_A, cmdb_service_id=uuid4(),
                    otel_service_name="tenant-a-service", environment="test",
                ),
                ServiceBinding(
                    id=binding_ids[1], tenant_id=TENANT_B, cmdb_service_id=uuid4(),
                    otel_service_name="tenant-b-service", environment="test",
                ),
                Evidence(
                    id=evidence_ids[0], tenant_id=TENANT_A, incident_id=INCIDENT,
                    investigation_id=investigation_ids[0], source_type="logs",
                    source_ref="tenant-a-evidence", summary=None,
                    observed_at=datetime.now(timezone.utc),
                ),
                Evidence(
                    id=evidence_ids[1], tenant_id=TENANT_B, incident_id=INCIDENT,
                    investigation_id=investigation_ids[1], source_type="logs",
                    source_ref="tenant-b-evidence", summary=None,
                    observed_at=datetime.now(timezone.utc),
                ),
                Evidence(
                    id=evidence_ids[2], tenant_id=TENANT_A, incident_id="other-incident",
                    investigation_id=investigation_ids[2], source_type="logs",
                    source_ref="tenant-a-other-incident", summary=None,
                    observed_at=datetime.now(timezone.utc),
                ),
            ])
            await session.commit()

    prepared = False
    try:
        asyncio.run(prepare())
        prepared = True
        yield factory
    finally:
        async def cleanup():
            if prepared:
                async with factory() as session:
                    await session.execute(delete(Evidence).where(Evidence.id.in_(evidence_ids)))
                    await session.execute(delete(ServiceBinding).where(ServiceBinding.id.in_(binding_ids)))
                    await session.commit()
            await engine.dispose()
        asyncio.run(cleanup())


def _signed_headers(path: str, tenant: UUID, *, forged_tenant: UUID) -> dict[str, str]:
    now = int(time.time())
    claims = {
        "iss": "trusted-gateway", "aud": "gamma-api", "sub": f"user:tenant-isolation-test:{tenant}",
        "actor_type": "user", "tenant_id": str(tenant), "tenant_access": True,
        "iat": now, "exp": now + 30, "jti": "pg-isolation-" + uuid4().hex,
        "method": "GET", "path": path,
        "evidence_incident_grants": [INCIDENT] if path == f"/api/v1/incidents/{INCIDENT}/evidence" else [],
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(
        hmac.new(b"s" * 48, encoded.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return {
        "X-Internal-API-Key": "service-secret",
        "X-Gateway-Principal": encoded + "." + signature,
        # Deliberately contradictory, untrusted browser headers:
        "X-Tenant-ID": str(forged_tenant),
        "X-Actor-ID": "forged-superadmin",
        "X-Actor-Role": "admin",
    }


@pytest.fixture(autouse=True)
def gateway_config(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "service-secret")
    monkeypatch.setattr(settings, "gateway_assertion_secret", "s" * 48)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "trusted-gateway")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-api")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)


@pytest.mark.parametrize("resource", ["bindings", "evidence"])
def test_real_http_routes_isolate_two_tenants_in_postgres(resource, tenant_postgres):
    factory = tenant_postgres

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        if resource == "bindings":
            path = "/api/v1/topology/bindings"
            field = "otel_service_name"
        else:
            path = f"/api/v1/incidents/{INCIDENT}/evidence"
            field = "source_ref"

        with TestClient(app) as client:
            a = client.get(path, headers=_signed_headers(path, TENANT_A, forged_tenant=TENANT_B))
            b = client.get(path, headers=_signed_headers(path, TENANT_B, forged_tenant=TENANT_A))

        assert a.status_code == 200, a.text
        assert b.status_code == 200, b.text
        assert [item[field] for item in a.json()] == [
            "tenant-a-service" if resource == "bindings" else "tenant-a-evidence"
        ]
        assert [item[field] for item in b.json()] == [
            "tenant-b-service" if resource == "bindings" else "tenant-b-evidence"
        ]
        assert a.headers["Cache-Control"] == "no-store"
        assert b.headers["Cache-Control"] == "no-store"
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.parametrize("resource", ["bindings", "evidence"])
def test_foreign_rows_and_foreign_incident_are_not_serialized(resource, tenant_postgres):
    factory = tenant_postgres

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        path = ("/api/v1/topology/bindings" if resource == "bindings"
                else f"/api/v1/incidents/{INCIDENT}/evidence")
        with TestClient(app) as client:
            response = client.get(
                path, headers=_signed_headers(path, TENANT_A, forged_tenant=TENANT_B)
            )
        assert response.status_code == 200, response.text
        values = [item["otel_service_name"] for item in response.json()] if resource == "bindings" \
            else [item["source_ref"] for item in response.json()]
        # Exact positive result prevents vacuous success on an empty response.
        expected = ["tenant-a-service" if resource == "bindings" else "tenant-a-evidence"]
        assert values == expected
        assert "tenant-b-service" not in values
        assert "tenant-b-evidence" not in values
        assert "tenant-a-other-incident" not in values
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://user:pass@localhost/production",
    "postgresql+asyncpg://user:pass@localhost/gamma_staging",
    "sqlite+aiosqlite:///tmp/gamma_tenant_test",
    "postgresql+asyncpg://user:pass@db.internal/gamma_tenant_test",
    "postgresql+asyncpg://user:pass@localhost/gamma_tenant_test?host=db.internal",
    "postgresql+asyncpg://user:pass@localhost/gamma_tenant_test?host=/var/run/postgresql",
    "postgresql+asyncpg://user:pass@localhost/gamma_tenant_test?sslmode=require",
])
def test_tenant_integration_refuses_unsafe_database_urls(url):
    with pytest.raises(pytest.fail.Exception):
        _require_disposable_url(url)


def test_signed_gateway_assertions_use_distinct_actors_and_tenants():
    path = "/api/v1/topology/bindings"
    a = _signed_headers(path, TENANT_A, forged_tenant=TENANT_B)
    b = _signed_headers(path, TENANT_B, forged_tenant=TENANT_A)
    def claims(headers):
        encoded = headers["X-Gateway-Principal"].split(".", 1)[0]
        return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    ca, cb = claims(a), claims(b)
    assert ca["sub"] != cb["sub"]
    assert ca["tenant_id"] != cb["tenant_id"]
    assert ca["jti"] != cb["jti"]
    assert ca["method"] == cb["method"] == "GET"
    assert ca["path"] == cb["path"] == path


def test_tenant_integration_accepts_only_explicit_loopback_test_database():
    url = "postgresql+asyncpg://test:test@localhost/gamma_tenant_test"
    assert _require_disposable_url(url) == url
