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
import httpx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import get_session
from app.main import app
from app.models import Evidence, InboxEvent, OutboxEvent, ServiceBinding
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
            for table in (Evidence.__tablename__, ServiceBinding.__tablename__,
                          InboxEvent.__tablename__, OutboxEvent.__tablename__):
                if await conn.scalar(text("select to_regclass(:table)"), {"table": table}) is None:
                    pytest.fail(f"Missing migrated table: {table}")
                if await conn.scalar(text(f"select count(*) from {table}")) != 0:
                    pytest.fail(f"Disposable table {table} must be empty before testing")
    async def clean():
        try:
            if written_ids:
                async with factory() as session:
                    await session.execute(delete(Evidence).where(Evidence.id.in_([UUID(row_id) for row_id in written_ids])))
                    await session.commit()
        finally:
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
    async def exercise():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            for tenant, other, marker in (
                (tenant_a, tenant_b, "tenant-a"), (tenant_b, tenant_a, "tenant-b")
            ):
                payload = {
                    "investigation_id": str(uuid4()), "source_type": "logs",
                    "source_ref": "ci-e2e-" + marker,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
                response = await client.post(
                    path,
                    headers=_headers("POST", path, tenant, [incident], forged_tenant=other),
                    json=payload,
                )
                assert response.status_code == 201, response.text
                assert response.headers["cache-control"] == "no-store"
                written_ids.append(response.json()["id"])
            assert await persisted_count() == 2
            for tenant, other, expected in (
                (tenant_a, tenant_b, "ci-e2e-tenant-a"),
                (tenant_b, tenant_a, "ci-e2e-tenant-b"),
            ):
                response = await client.get(
                    path, headers=_headers("GET", path, tenant, [incident], forged_tenant=other)
                )
                assert response.status_code == 200, response.text
                assert response.headers["cache-control"] == "no-store"
                assert [r["source_ref"] for r in response.json()] == [expected]
            denied_read = await client.get(
                path, headers=_headers("GET", path, tenant_a, [], forged_tenant=tenant_b)
            )
            assert denied_read.status_code == 403, denied_read.text
            assert denied_read.headers["cache-control"] == "no-store"
            denied = await client.post(
                path, headers=_headers("POST", path, tenant_b, [], forged_tenant=tenant_a),
                json={
                    "investigation_id": str(uuid4()), "source_type": "logs",
                    "source_ref": "should-not-persist",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            assert denied.status_code == 403, denied.text
            assert denied.headers["cache-control"] == "no-store"
            assert await persisted_count() == 2
            # A valid grant cannot be transplanted to another HTTP path.
            mismatched = await client.get(
                path, headers=_headers(
                    "GET", "/api/v1/incidents/other/evidence",
                    tenant_a, [incident], forged_tenant=tenant_b,
                )
            )
            assert mismatched.status_code == 401, mismatched.text
    try:
        asyncio.run(exercise())
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_http_postgres_alert_inbox_outbox_and_relay(database, monkeypatch):
    """Real PG HTTP ingestion, tenant deduplication and locally mocked delivery."""
    from app import outbox_relay

    factory, _ = database
    monkeypatch.setattr(settings, "enable_alert_ingestion", True)
    monkeypatch.setattr(outbox_relay, "get_session_factory", lambda: factory)
    tenant_a, tenant_b = uuid4(), uuid4()
    path = "/api/v1/integrations/opensearch/alerts"
    payload = {
        "external_event_id": "ci-alert-shared-key", "source": "opensearch",
        "service_name": "checkout", "severity": "major", "status": "firing",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "evidence_refs": ["otel:trace-ci"],
    }
    received = []
    created = []
    published_ids = []

    async def session_override():
        async with factory() as session:
            yield session

    def receiver(request):
        body = json.loads(request.content)
        assert request.headers["x-event-id"] == body["event_id"]
        assert request.headers["authorization"] == "Bearer ci-ephemeral-token"
        assert body["tenant_id"] in (str(tenant_a), str(tenant_b))
        assert body["event_type"] == "observability.alert.firing"
        assert body["aggregate_id"] == "checkout"
        received.append(body)
        return httpx.Response(202)

    async def rows():
        async with factory() as session:
            inbox = (await session.scalars(
                select(InboxEvent).where(InboxEvent.tenant_id.in_((tenant_a, tenant_b)))
            )).all()
            outbox = (await session.scalars(
                select(OutboxEvent).where(OutboxEvent.tenant_id.in_((tenant_a, tenant_b)))
            )).all()
            return inbox, outbox

    async def exercise():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as api:
            for tenant, other in ((tenant_a, tenant_b), (tenant_b, tenant_a)):
                first = await api.post(
                    path, headers=_headers("POST", path, tenant, [], forged_tenant=other),
                    json=payload,
                )
                assert first.status_code == 200, first.text
                assert first.headers["cache-control"] == "no-store"
                assert first.json()["duplicate"] is False
                created.append(first.json()["id"])

                retry = await api.post(
                    path, headers=_headers("POST", path, tenant, [], forged_tenant=other),
                    json=payload,
                )
                assert retry.status_code == 200, retry.text
                assert retry.json() == {"id": first.json()["id"], "duplicate": True}
                conflicting = await api.post(
                    path, headers=_headers("POST", path, tenant, [], forged_tenant=other),
                    json={**payload, "severity": "critical"},
                )
                assert conflicting.status_code == 409, conflicting.text
                assert conflicting.headers["cache-control"] == "no-store"

            inbox, outbox = await rows()
            assert {str(row.id) for row in inbox} == set(created)
            assert len(outbox) == len(inbox) == 2
            assert {row.tenant_id for row in outbox} == {tenant_a, tenant_b}
            assert all(row.published_at is None and row.attempts == 0 for row in outbox)
            published_ids.extend(row.id for row in outbox)
            async with httpx.AsyncClient(transport=httpx.MockTransport(receiver)) as downstream:
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is True
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is True
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is False
            assert len(received) == 2
            assert {row["event_id"] for row in received} == {str(i) for i in published_ids}
            _, final_outbox = await rows()
            assert len(final_outbox) == 2
            assert all(row.published_at is not None and row.attempts == 0 for row in final_outbox)
    app.dependency_overrides[get_session] = session_override
    try:
        asyncio.run(exercise())
    finally:
        app.dependency_overrides.pop(get_session, None)
        async def cleanup():
            # Preflight required empty tables. Unique tenants are allocated only
            # for this test, so cleanup also covers partially successful writes
            # whose HTTP response never returned an ID.
            async with factory() as session:
                await session.execute(
                    delete(OutboxEvent).where(OutboxEvent.tenant_id.in_((tenant_a, tenant_b)))
                )
                await session.execute(
                    delete(InboxEvent).where(InboxEvent.tenant_id.in_((tenant_a, tenant_b)))
                )
                await session.commit()
        asyncio.run(cleanup())
