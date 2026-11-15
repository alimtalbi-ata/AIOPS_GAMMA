"""Real PostgreSQL HTTP evidence create/read isolation qualification.

Requires a fresh, empty, explicitly disposable PostgreSQL 16 database prepared
by Alembic head. This is NOT a production gateway or upstream ACL test.
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
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import get_session
from app.main import app
from app.models import Evidence, ServiceBinding
from app.settings import settings


def _disposable_database_url():
    raw = os.environ.get("GAMMA_TENANT_TEST_DATABASE_URL", "")
    if not raw:
        pytest.fail("GAMMA_TENANT_TEST_DATABASE_URL must be supplied for this E2E suite")
    if os.environ.get("GAMMA_TENANT_TEST_ALLOW_WRITE") != "I_UNDERSTAND_DISPOSABLE_DB":
        pytest.fail("Explicit disposable database write acknowledgement required")
    try:
        url = make_url(raw)
        _ = url.port
    except (ArgumentError, ValueError, TypeError) as exc:
        pytest.fail(f"Malformed database URL: {type(exc).__name__}")
    if (url.drivername != "postgresql+asyncpg" or url.query
            or url.host not in ("127.0.0.1", "localhost", "::1")
            or not url.database or not url.database.endswith("_tenant_test")):
        pytest.fail("Refusing unsafe tenant database URL")
    return raw


@pytest.fixture
def database(monkeypatch):
    raw = _disposable_database_url()
    engine = create_async_engine(raw, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    written_ids = []
    async def preflight():
        async with engine.connect() as conn:
            name = await conn.scalar(text("select current_database()"))
            address = await conn.scalar(text("select inet_server_addr()"))
            version = await conn.scalar(text("show server_version_num"))
            revision = await conn.scalar(text("select version_num from alembic_version"))
            role = await conn.scalar(text("select rolsuper from pg_roles where rolname=current_user"))
            if (not name or not name.endswith("_tenant_test") or address is None
                    or not ip_address(str(address)).is_loopback or role is not False
                    or not 160000 <= int(version) < 170000
                    or revision != "0002_gateway_replay"):
                pytest.fail("Connected PostgreSQL identity or migration is not approved")
            for table in (Evidence.__tablename__, ServiceBinding.__tablename__):
                if await conn.scalar(text("select to_regclass(:table)"), {"table": table}) is None:
                    pytest.fail(f"Missing migrated table: {table}")
                if await conn.scalar(text(f"select count(*) from {table}")) != 0:
                    pytest.fail(f"Disposable table {table} must be empty before testing")
    async def clean():
        async with factory() as session:
            if written_ids:
                await session.execute(delete(Evidence).where(Evidence.id.in_([UUID(row_id) for row_id in written_ids])))
                await session.commit()
        await engine.dispose()
    monkeypatch.setattr(settings, "internal_api_key", "ci-service-key")
    monkeypatch.setattr(settings, "gateway_assertion_secret", "g" * 48)
    monkeypatch.setattr(settings, "gateway_assertion_issuer", "ci-independent-issuer")
    monkeypatch.setattr(settings, "gateway_assertion_audience", "gamma-ci")
    monkeypatch.setattr(settings, "gateway_assertion_max_ttl_seconds", 60)
    try:
        asyncio.run(preflight())
        yield factory, written_ids
    finally:
        asyncio.run(clean())


def _headers(method, path, tenant, grants, *, forged_tenant):
    """An independent minimal HMAC emitter; no application signing helpers."""
    now = int(time.time())
    claims = {
        "iss": "ci-independent-issuer", "aud": "gamma-ci",
        "sub": "ci-user-" + str(tenant), "actor_type": "user",
        "tenant_id": str(tenant), "tenant_access": True,
        "iat": now, "exp": now + 30, "jti": "ci-" + uuid4().hex,
        "method": method, "path": path, "evidence_incident_grants": grants,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    sig = base64.urlsafe_b64encode(
        hmac.new(b"g" * 48, encoded.encode("ascii"), hashlib.sha256).digest()
    ).rstrip(b"=").decode("ascii")
    return {
        "X-Gateway-Principal": encoded + "." + sig,
        "X-Internal-API-Key": "ci-service-key",
        "X-Tenant-ID": str(forged_tenant),
        "X-Actor-ID": "forged-admin",
    }


def test_http_postgres_two_tenants_write_read_and_denied_write_is_atomic(database):
    factory, written_ids = database
    tenant_a, tenant_b = uuid4(), uuid4()
    incident = "shared-ci-e2e-incident"
    path = f"/api/v1/incidents/{incident}/evidence"

    async def session_override():
        async with factory() as session:
            yield session

    async def persisted_count():
        async with factory() as session:
            return await session.scalar(select(func.count()).select_from(Evidence))

    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            for tenant, other, marker in (
                (tenant_a, tenant_b, "tenant-a"), (tenant_b, tenant_a, "tenant-b")
            ):
                payload = {
                    "investigation_id": str(uuid4()), "source_type": "logs",
                    "source_ref": "ci-e2e-" + marker,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
                response = client.post(
                    path,
                    headers=_headers("POST", path, tenant, [incident], forged_tenant=other),
                    json=payload,
                )
                assert response.status_code == 201, response.text
                assert response.headers["cache-control"] == "no-store"
                written_ids.append(response.json()["id"])
            assert asyncio.run(persisted_count()) == 2
            for tenant, other, expected in (
                (tenant_a, tenant_b, "ci-e2e-tenant-a"),
                (tenant_b, tenant_a, "ci-e2e-tenant-b"),
            ):
                response = client.get(
                    path, headers=_headers("GET", path, tenant, [incident], forged_tenant=other)
                )
                assert response.status_code == 200, response.text
                assert response.headers["cache-control"] == "no-store"
                assert [r["source_ref"] for r in response.json()] == [expected]
            denied = client.post(
                path, headers=_headers("POST", path, tenant_b, [], forged_tenant=tenant_a),
                json={
                    "investigation_id": str(uuid4()), "source_type": "logs",
                    "source_ref": "should-not-persist",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            assert denied.status_code == 403, denied.text
            assert denied.headers["cache-control"] == "no-store"
            assert asyncio.run(persisted_count()) == 2
            # A valid grant cannot be transplanted to another HTTP path.
            mismatched = client.get(
                path, headers=_headers(
                    "GET", "/api/v1/incidents/other/evidence",
                    tenant_a, [incident], forged_tenant=tenant_b,
                )
            )
            assert mismatched.status_code == 401, mismatched.text
    finally:
        app.dependency_overrides.pop(get_session, None)
