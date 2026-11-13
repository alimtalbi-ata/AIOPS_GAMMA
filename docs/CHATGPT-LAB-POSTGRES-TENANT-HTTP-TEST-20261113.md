# Disposable PostgreSQL HTTP tenant-isolation test

Test module: `tests/test_resource_list_http_postgres.py`

This suite drives the **real FastAPI application routes** for tenant-owned
ServiceBinding and Evidence list operations, backed by actual PostgreSQL
sessions. It seeds tenant A and tenant B rows, sends independently signed
request-bound gateway assertions for two **distinct actor subjects**, deliberately supplies contradictory
browser-controlled tenant/actor/role headers, and asserts each response
contains only the authenticated tenant's rows. Evidence is additionally
scoped to the requested incident.

## Safety gates

The test refuses to insert any rows unless all conditions hold:

- Explicit `GAMMA_TENANT_TEST_DATABASE_URL` using `postgresql+asyncpg`.
- Database name ends in `_tenant_test`.
- Host is loopback only: localhost, 127.0.0.1 or ::1.\n- **No URL query parameters** (e.g. `?host=db.internal` or Unix socket\n  `?host=/var/run/postgresql`); such parameters can override the host that\n  appears in the URL authority.
- `GAMMA_TENANT_TEST_ALLOW_WRITE=I_UNDERSTAND_DISPOSABLE_DB`.
- Connected database name independently matches the suffix.
- The **actual PostgreSQL TCP server address** reported by `inet_server_addr()`
  must be IPv4/IPv6 loopback (Unix sockets are refused).
- The connected PostgreSQL role must **not** be a superuser.
- The connected server must be **PostgreSQL 16**.
- Alembic revision is exactly `0002_gateway_replay`.
- Required tables exist and are empty before test data is inserted.
- SQLAlchemy uses `NullPool`; cleanup deletes only the exact generated row IDs.

Provision a **new, isolated disposable local PostgreSQL database** and apply
the reviewed migrations to it before testing. Do not use a shared development
database, a port-forward, staging, production, or the production Debian host.
Do not set GAMMA's normal `DATABASE_URL` to this target.

## Command

```bash
GAMMA_TENANT_TEST_ALLOW_WRITE=I_UNDERSTAND_DISPOSABLE_DB \
GAMMA_TENANT_TEST_DATABASE_URL='postgresql+asyncpg://test_user:...@localhost/gamma_tenant_test' \
  python -m pytest -q tests/test_resource_list_http_postgres.py
```

Expected test cases: 13 (four PostgreSQL HTTP cases, seven unsafe-URL\ncases, one safe-URL case and one distinct-actor signing case). The test intentionally skips when the
dedicated URL is absent; unsafe configured URLs fail. A skipped test is not a
pass.

## What this proves — and does not prove

When executed against the disposable database, this suite proves actual
PostgreSQL-backed HTTP list isolation for these two GAMMA resource routes and
that contradictory untrusted headers do not override the signed tenant claim.

It does **not** qualify the real IdP, gateway membership lookup, Core/Evidence/
Twin source-side ACL, PostgreSQL RLS, assertion replay protection, GLPI entity
permissions, aggregates/graphs, or any LIVE route. It does not enable
canonical reads. Existing deny-before-database HTTP tests remain separate.

## Current execution status

**Committed, NOT EXECUTED against PostgreSQL.** The ChatGPT internal lab has
not been provisioned with a disposable PostgreSQL server or an authenticated
full repository checkout. No database was contacted or created in this work
cycle. Do not describe this test as passing until its actual output, database
identity and exact commit SHA have been recorded.
