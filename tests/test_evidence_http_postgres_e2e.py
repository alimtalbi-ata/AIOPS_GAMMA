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
from uuid import uuid4

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
    written_tenants = []
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
            if written_tenants:
                async with factory() as session:
                    await session.execute(
                        delete(Evidence).where(Evidence.tenant_id.in_(written_tenants))
                    )
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
        yield factory, written_tenants
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
    factory, written_tenants = database
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
                # Register the isolated tenant before the write: cleanup must
                # cover a committed insert even if the HTTP response is lost.
                written_tenants.append(tenant)
                response = await client.post(
                    path,
                    headers=_headers("POST", path, tenant, [incident], forged_tenant=other),
                    json=payload,
                )
                assert response.status_code == 201, response.text
                assert response.headers["cache-control"] == "no-store"
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
    monkeypatch.setenv("CORRELATION_WEBHOOK_ALLOWED_HOST", "receiver.example.test")
    from app import outbox_relay

    factory, _ = database
    # Exercise the default fail-closed switch before enabling ingestion.
    monkeypatch.setattr(settings, "enable_alert_ingestion", False)
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
            disabled = await api.post(
                path, headers=_headers("POST", path, tenant_a, [], forged_tenant=tenant_b),
                json=payload,
            )
            assert disabled.status_code == 503, disabled.text
            assert disabled.headers["cache-control"] == "no-store"
            disabled_inbox, disabled_outbox = await rows()
            assert not disabled_inbox and not disabled_outbox
            monkeypatch.setattr(settings, "enable_alert_ingestion", True)

            # Neither caller-selected identity headers nor an assertion bound
            # to another HTTP method can create tenant-scoped alert records.
            unsigned = await api.post(
                path,
                headers={
                    "X-Internal-API-Key": "ci-service-key",
                    "X-Tenant-ID": str(tenant_a),
                    "X-Actor-ID": "forged-admin",
                },
                json=payload,
            )
            assert unsigned.status_code == 401, unsigned.text
            assert unsigned.headers["cache-control"] == "no-store"
            wrong_method = await api.post(
                path,
                headers=_headers("GET", path, tenant_a, [], forged_tenant=tenant_b),
                json=payload,
            )
            assert wrong_method.status_code == 401, wrong_method.text
            assert wrong_method.headers["cache-control"] == "no-store"
            unauthorized_inbox, unauthorized_outbox = await rows()
            assert not unauthorized_inbox and not unauthorized_outbox

            # A signed tenant assertion is not a substitute for the separate
            # workload credential; neither a missing nor a wrong key may write.
            signed = _headers("POST", path, tenant_a, [], forged_tenant=tenant_b)
            for bad_key in (None, "incorrect-service-key"):
                headers = {**signed}
                if bad_key is None:
                    headers.pop("X-Internal-API-Key")
                else:
                    headers["X-Internal-API-Key"] = bad_key
                rejected = await api.post(path, headers=headers, json=payload)
                assert rejected.status_code == 401, rejected.text
                assert rejected.headers["cache-control"] == "no-store"
            no_key_inbox, no_key_outbox = await rows()
            assert not no_key_inbox and not no_key_outbox

            # Conflicting duplicate security headers must not depend on which
            # header a proxy, ASGI server or framework happens to choose.
            for duplicate_name, duplicate_value in (
                ("X-Internal-API-Key", "incorrect-service-key"),
                ("X-Gateway-Principal", "forged-principal"),
                ("X-Tenant-ID", str(tenant_b)),
                ("X-Actor-ID", "forged-second-actor"),
            ):
                duplicate_headers = list(signed.items()) + [
                    (duplicate_name, duplicate_value)
                ]
                ambiguous = await api.post(
                    path, headers=duplicate_headers, json=payload
                )
                assert ambiguous.status_code == 401, (
                    duplicate_name, ambiguous.text
                )
                assert ambiguous.headers["cache-control"] == "no-store"
            duplicate_inbox, duplicate_outbox = await rows()
            assert not duplicate_inbox and not duplicate_outbox
            for tenant, other in ((tenant_a, tenant_b), (tenant_b, tenant_a)):
                # Same external key may legitimately carry different content
                # in a different tenant; deduplication must be tenant-scoped.
                tenant_payload = (
                    payload if tenant == tenant_a else {**payload, "severity": "critical"}
                )
                first = await api.post(
                    path, headers=_headers("POST", path, tenant, [], forged_tenant=other),
                    json=tenant_payload,
                )
                assert first.status_code == 200, first.text
                assert first.headers["cache-control"] == "no-store"
                assert first.json()["duplicate"] is False
                created.append(first.json()["id"])

                retry = await api.post(
                    path, headers=_headers("POST", path, tenant, [], forged_tenant=other),
                    json=tenant_payload,
                )
                assert retry.status_code == 200, retry.text
                assert retry.json() == {"id": first.json()["id"], "duplicate": True}
                conflicting = await api.post(
                    path, headers=_headers("POST", path, tenant, [], forged_tenant=other),
                    json={**tenant_payload, "severity": "minor"},
                )
                assert conflicting.status_code == 409, conflicting.text
                assert conflicting.headers["cache-control"] == "no-store"

            inbox, outbox = await rows()
            assert {str(row.id) for row in inbox} == set(created)
            assert len(outbox) == len(inbox) == 2
            assert {row.tenant_id for row in outbox} == {tenant_a, tenant_b}
            # Inbox/outbox must carry the same tenant-specific payload;
            # matching row counts alone cannot detect cross-tenant leakage.
            inbox_by_tenant = {row.tenant_id: row for row in inbox}
            outbox_by_tenant = {row.tenant_id: row for row in outbox}
            assert len(inbox_by_tenant) == len(outbox_by_tenant) == 2
            for tenant in (tenant_a, tenant_b):
                assert outbox_by_tenant[tenant].payload == inbox_by_tenant[tenant].payload
                assert outbox_by_tenant[tenant].event_type == "observability.alert.firing"
                assert outbox_by_tenant[tenant].aggregate_id == "checkout"
            assert {
                row.tenant_id: row.payload["severity"] for row in inbox
            } == {tenant_a: "major", tenant_b: "critical"}
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
            # Check the actual downstream HTTP envelopes, not only the
            # database rows and delivery count. Tenant-specific severity must
            # survive serialization and dispatch without cross-tenant mixing.
            delivered_by_id = {item["event_id"]: item for item in received}
            for event in outbox:
                envelope = delivered_by_id[str(event.id)]
                assert envelope["tenant_id"] == str(event.tenant_id)
                assert envelope["payload"] == event.payload
                assert envelope["event_type"] == event.event_type
                assert envelope["aggregate_id"] == event.aggregate_id
            _, final_outbox = await rows()
            assert len(final_outbox) == 2
            assert all(row.published_at is not None and row.attempts == 0 for row in final_outbox)
            # A transient downstream 503 must retain the event and schedule a
            # retry; only a subsequent 2xx may mark it as published.
            transient = await api.post(
                path,
                headers=_headers("POST", path, tenant_a, [], forged_tenant=tenant_b),
                json={**payload, "external_event_id": "ci-alert-transient-retry"},
            )
            assert transient.status_code == 200, transient.text
            assert transient.json()["duplicate"] is False
            _, pending = await rows()
            retry_event = next(row for row in pending if row.published_at is None)
            attempts_seen = []

            def unavailable(request):
                attempts_seen.append(request.headers["x-event-id"])
                return httpx.Response(503)

            dispatch_started_at = datetime.now(timezone.utc)
            async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as downstream:
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is True
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is False
            assert attempts_seen == [str(retry_event.id)]
            _, deferred = await rows()
            failed = next(row for row in deferred if row.id == retry_event.id)
            assert failed.published_at is None
            assert failed.attempts == 1
            assert failed.next_attempt_at is not None
            # The first retry is scheduled two seconds after dispatch time,
            # not relative to the event's potentially older creation time.
            assert dispatch_started_at < failed.next_attempt_at
            assert (failed.next_attempt_at - datetime.now(timezone.utc)).total_seconds() > 0
            assert (failed.next_attempt_at - dispatch_started_at).total_seconds() < 60
            assert failed.last_error

            # Advance eligibility explicitly in this disposable DB rather than
            # sleeping or relying on wall-clock timing in CI.
            async with factory() as session:
                row = await session.get(OutboxEvent, retry_event.id)
                row.next_attempt_at = None
                await session.commit()
            async with httpx.AsyncClient(transport=httpx.MockTransport(receiver)) as downstream:
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is True
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is False
            _, recovered = await rows()
            delivered = next(row for row in recovered if row.id == retry_event.id)
            assert delivered.published_at is not None
            assert delivered.attempts == 1
            assert delivered.next_attempt_at is None
            assert delivered.last_error is None

            # Two independent HTTP requests race on the same tenant/source/key.
            # PostgreSQL's unique constraint must yield one insert and one
            # idempotent duplicate, never two inbox/outbox pairs.
            concurrent_payload = {
                **payload, "external_event_id": "ci-alert-concurrent-" + uuid4().hex,
            }

            async def concurrent_ingest():
                return await api.post(
                    path,
                    headers=_headers("POST", path, tenant_b, [], forged_tenant=tenant_a),
                    json=concurrent_payload,
                )

            left, right = await asyncio.gather(concurrent_ingest(), concurrent_ingest())
            assert left.status_code == right.status_code == 200, (left.text, right.text)
            assert left.json()["id"] == right.json()["id"]
            assert {left.json()["duplicate"], right.json()["duplicate"]} == {False, True}
            inbox_after, outbox_after = await rows()
            matching_inbox = [
                row for row in inbox_after
                if row.tenant_id == tenant_b
                and row.external_event_id == concurrent_payload["external_event_id"]
            ]
            assert len(matching_inbox) == 1
            assert len(inbox_after) == len(outbox_after) == 4

            # Conflicting payloads racing for the same idempotency key must
            # never both succeed: the winning payload is immutable.
            conflicting_key = "ci-alert-racing-conflict-" + uuid4().hex

            async def conflicting_ingest(severity):
                return await api.post(
                    path,
                    headers=_headers("POST", path, tenant_a, [], forged_tenant=tenant_b),
                    json={
                        **payload,
                        "external_event_id": conflicting_key,
                        "severity": severity,
                    },
                )

            first_conflict, second_conflict = await asyncio.gather(
                conflicting_ingest("major"), conflicting_ingest("critical")
            )
            assert sorted((first_conflict.status_code, second_conflict.status_code)) == [200, 409], (
                first_conflict.text, second_conflict.text
            )
            assert first_conflict.headers["cache-control"] == "no-store"
            assert second_conflict.headers["cache-control"] == "no-store"
            final_inbox, final_outbox = await rows()
            matching_conflict = [
                row for row in final_inbox
                if row.tenant_id == tenant_a and row.external_event_id == conflicting_key
            ]
            assert len(matching_conflict) == 1
            assert matching_conflict[0].payload["severity"] in ("major", "critical")
            assert len(final_inbox) == len(final_outbox) == 5

            # The concurrent-ingestion scenarios left two older unpublished
            # events. Drain them first: dispatch_once selects the oldest
            # eligible event, not necessarily the newly inserted redirect.
            pending_before_redirect = [row for row in final_outbox if row.published_at is None]
            assert len(pending_before_redirect) == 2
            drained_ids = {str(row.id) for row in pending_before_redirect}
            # Force a timestamp tie to exercise the stable UUID tiebreaker.
            # This protects ordering against identical database timestamp values.
            tied_created_at = min(row.created_at for row in pending_before_redirect)
            async with factory() as session:
                for pending in pending_before_redirect:
                    row = await session.get(OutboxEvent, pending.id)
                    row.created_at = tied_created_at
                await session.commit()
            expected_drain_order = sorted(drained_ids)
            received_before_drain = len(received)
            async with httpx.AsyncClient(transport=httpx.MockTransport(receiver)) as downstream:
                for _ in pending_before_redirect:
                    assert await outbox_relay.dispatch_once(
                        downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                    ) is True
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is False
            assert [row["event_id"] for row in received[received_before_drain:]] == expected_drain_order
            _, drained_outbox = await rows()
            assert all(row.published_at is not None for row in drained_outbox)

            # A receiver redirect is not an acknowledgement. In particular,
            # the relay must not follow it and forward its bearer token.
            redirected = await api.post(
                path,
                headers=_headers("POST", path, tenant_a, [], forged_tenant=tenant_b),
                json={**payload, "external_event_id": "ci-alert-redirect-" + uuid4().hex},
            )
            assert redirected.status_code == 200, redirected.text
            _, before_redirect = await rows()
            pending_before_redirect_delivery = [
                row for row in before_redirect if row.published_at is None
            ]
            assert len(pending_before_redirect_delivery) == 1
            redirect_event = pending_before_redirect_delivery[0]
            redirect_calls = []

            def redirect_receiver(request):
                redirect_calls.append(str(request.url))
                return httpx.Response(302, headers={"Location": "https://untrusted.example.test/"})

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(redirect_receiver), follow_redirects=True
            ) as downstream:
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is True
            assert redirect_calls == ["https://receiver.example.test/events"]
            _, after_redirect = await rows()
            pending_redirect = next(row for row in after_redirect if row.id == redirect_event.id)
            assert pending_redirect.published_at is None
            assert pending_redirect.attempts == 1
            assert pending_redirect.next_attempt_at is not None
            assert pending_redirect.last_error

            # A deferred retry must not be delivered early, even if the
            # receiver has recovered. This also proves the retry timestamp
            # actually gates selection rather than merely recording metadata.
            early_retry_calls = []

            def early_retry_receiver(request):
                early_retry_calls.append(request.headers["x-event-id"])
                return httpx.Response(202)

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(early_retry_receiver)
            ) as downstream:
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is False
            assert early_retry_calls == []
            _, deferred_rows = await rows()
            deferred_redirect = next(row for row in deferred_rows if row.id == redirect_event.id)
            assert deferred_redirect.published_at is None
            assert deferred_redirect.attempts == 1
            assert deferred_redirect.next_attempt_at is not None

            # Once retry eligibility is restored, a real 2xx acknowledgement
            # must publish the same event exactly once, with no stale retry.
            async with factory() as session:
                row = await session.get(OutboxEvent, redirect_event.id)
                row.next_attempt_at = None
                await session.commit()
            received_before = len(received)
            async with httpx.AsyncClient(transport=httpx.MockTransport(receiver)) as downstream:
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is True
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is False
            assert len(received) == received_before + 1
            assert received[-1]["event_id"] == str(redirect_event.id)
            _, after_redirect_recovery = await rows()
            recovered_redirect = next(
                row for row in after_redirect_recovery if row.id == redirect_event.id
            )
            assert recovered_redirect.published_at is not None
            assert recovered_redirect.attempts == 1
            assert recovered_redirect.next_attempt_at is None
            assert recovered_redirect.last_error is None

            # Exhausted deliveries must stop at MAX_ATTEMPTS: the relay may
            # neither spin forever nor deliver a dead-letter candidate again.
            exhausted = await api.post(
                path,
                headers=_headers("POST", path, tenant_b, [], forged_tenant=tenant_a),
                json={**payload, "external_event_id": "ci-alert-exhausted-" + uuid4().hex},
            )
            assert exhausted.status_code == 200, exhausted.text
            _, pending_exhaustion = await rows()
            exhausted_event = next(
                row for row in pending_exhaustion if row.published_at is None
            )
            async with factory() as session:
                row = await session.get(OutboxEvent, exhausted_event.id)
                row.attempts = 0
                row.next_attempt_at = None
                await session.commit()
            # A transport timeout on the first attempt must be retryable.
            # Verify persisted backoff and no immediate redelivery.
            timeout_retry_calls = []

            def retry_timeout_receiver(request):
                timeout_retry_calls.append(request.headers["x-event-id"])
                raise httpx.ReadTimeout("receiver timed out", request=request)

            timeout_started_at = datetime.now(timezone.utc)
            async with httpx.AsyncClient(transport=httpx.MockTransport(retry_timeout_receiver)) as downstream:
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is True
            timeout_completed_at = datetime.now(timezone.utc)
            assert timeout_retry_calls == [str(exhausted_event.id)]
            async with factory() as session:
                row = await session.get(OutboxEvent, exhausted_event.id)
                assert row.published_at is None
                assert row.attempts == 1
                assert row.next_attempt_at is not None
                # The deadline must be computed after the HTTP failure, not
                # against the original event creation time.
                assert timeout_started_at + outbox_relay.retry_delay(1) <= row.next_attempt_at
                assert row.next_attempt_at <= timeout_completed_at + outbox_relay.retry_delay(1)
                assert "timed out" in row.last_error
                # Hold this disposable event beyond the test's wall-clock
                # duration so a slow CI runner cannot cause a flaky retry.
                row.next_attempt_at = datetime.now(timezone.utc) + outbox_relay.retry_delay(9)
                await session.commit()
            async with httpx.AsyncClient(transport=httpx.MockTransport(retry_timeout_receiver)) as downstream:
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is False
            assert timeout_retry_calls == [str(exhausted_event.id)]
            async with factory() as session:
                row = await session.get(OutboxEvent, exhausted_event.id)
                # Simulate elapsed backoff without waiting on the CI clock.
                row.next_attempt_at = None
                await session.commit()
            recovered_calls = []

            def recovered_receiver(request):
                recovered_calls.append({
                    "method": request.method,
                    "url": str(request.url),
                    "content_type": request.headers["content-type"],
                    "event_id": request.headers["x-event-id"],
                    "authorization": request.headers["authorization"],
                    "body": request.content,
                })
                return httpx.Response(202)

            async with httpx.AsyncClient(transport=httpx.MockTransport(recovered_receiver)) as downstream:
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is True
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is False
            assert len(recovered_calls) == 1
            assert recovered_calls[0]["method"] == "POST"
            assert recovered_calls[0]["url"] == "https://receiver.example.test/events"
            assert recovered_calls[0]["content_type"] == "application/json"
            assert recovered_calls[0]["event_id"] == str(exhausted_event.id)
            assert recovered_calls[0]["authorization"] == "Bearer ci-ephemeral-token"
            recovered_body = json.loads(recovered_calls[0]["body"])
            assert recovered_body["event_id"] == str(exhausted_event.id)
            assert recovered_body["tenant_id"] == str(exhausted_event.tenant_id)
            assert recovered_body["event_type"] == exhausted_event.event_type
            assert recovered_body["aggregate_id"] == exhausted_event.aggregate_id
            assert recovered_body["payload"] == exhausted_event.payload
            async with factory() as session:
                row = await session.get(OutboxEvent, exhausted_event.id)
                assert row.published_at is not None
                assert row.attempts == 1
                assert row.next_attempt_at is None
                assert row.last_error is None
                # Re-arm the disposable row for terminal timeout coverage.
                row.published_at = None
                row.attempts = outbox_relay.MAX_ATTEMPTS - 1
                row.next_attempt_at = None
                await session.commit()
            # A transport timeout at the final attempt must be persisted as
            # a terminal failure, not escape or mark the event delivered.
            timeout_calls = []

            def timed_out_receiver(request):
                timeout_calls.append(request.headers["x-event-id"])
                raise httpx.ReadTimeout("receiver timed out", request=request)

            async with httpx.AsyncClient(transport=httpx.MockTransport(timed_out_receiver)) as downstream:
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is True
            assert timeout_calls == [str(exhausted_event.id)]
            async with factory() as session:
                row = await session.get(OutboxEvent, exhausted_event.id)
                assert row.published_at is None
                assert row.attempts == outbox_relay.MAX_ATTEMPTS
                assert row.next_attempt_at is None
                assert "timed out" in row.last_error
            # The inspection session is closed: no row lock can mask a
            # wrongly eligible terminal event during this second dispatch.
            async with httpx.AsyncClient(transport=httpx.MockTransport(timed_out_receiver)) as downstream:
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is False
            assert timeout_calls == [str(exhausted_event.id)]
            async with factory() as session:
                row = await session.get(OutboxEvent, exhausted_event.id)
                # Re-arm the disposable row to exercise HTTP 503 exhaustion too.
                row.attempts = outbox_relay.MAX_ATTEMPTS - 1
                row.next_attempt_at = None
                await session.commit()
            terminal_calls = []

            def terminal_receiver(request):
                terminal_calls.append(request.headers["x-event-id"])
                return httpx.Response(503)

            async with httpx.AsyncClient(transport=httpx.MockTransport(terminal_receiver)) as downstream:
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is True
                assert await outbox_relay.dispatch_once(
                    downstream, "https://receiver.example.test/events", "ci-ephemeral-token"
                ) is False
            assert terminal_calls == [str(exhausted_event.id)]
            _, terminal_rows = await rows()
            terminal = next(row for row in terminal_rows if row.id == exhausted_event.id)
            assert terminal.published_at is None
            assert terminal.attempts == outbox_relay.MAX_ATTEMPTS
            assert terminal.next_attempt_at is None
            assert terminal.last_error
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
