# Migration et exploitation

## Database

For a **fresh database** use:

```bash
docker compose run --rm api alembic upgrade head
```

Do not run `app.init_db` after adopting Alembic. For an existing database already created with `create_all`, **do not run the initial migration directly**: first compare its schema to `0001_initial`, add the new outbox columns, and then `alembic stamp 0001_initial` after manual verification. Back up PostgreSQL before any schema change. Never use `alembic downgrade` on production without review.

## Outbox relay

Configure `CORRELATION_WEBHOOK_URL` (HTTPS) and `CORRELATION_WEBHOOK_TOKEN` only after your existing correlation engine exposes a trusted, idempotent receiver. The worker uses PostgreSQL row locking, retries, and stops after 10 failed attempts; failed events require operator review. Its delivery semantics are **at least once**.

```bash
docker compose --profile relay up -d outbox-relay
```

## Telemetry

The optional OTel Collector demo receives OTLP on 4317/4318 on loopback and forwards traces/logs to the official Data Prepper endpoint (not part of this Compose file). The official stack and its pipeline definitions must be installed and pinned separately. Collector is not activated by default.

## Production gaps

No full CMDB sync or automatic RCA yet. Implement tenant-aware PromQL, real OAuth2 service identities, audit logging, OpenSearch DLS and data retention before production. Disable experimental features instantly via feature flags during rollback.
