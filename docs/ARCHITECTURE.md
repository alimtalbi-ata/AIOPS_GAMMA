# Blueprint AIOPS_GAMMA — OpenSearch Observability

## Existing platform (preserved)

Python/FastAPI services; PostgreSQL; Docker Compose; current log/metric collection, alert correlation, Service Map/CMDB, RCA and AI/LLM agents. No existing module was inspected or copied: this repository provides integration points until existing source is supplied.

## Data planes

1. Existing collection remains primary.
2. OTLP dual-export to pinned official Observability stack is an **upcoming integration**, not provided by the demo single-node OpenSearch.
3. FastAPI queries tenant-scoped OpenSearch indexes via Query DSL.
4. PostgreSQL stores tenant-local inbox/outbox, CMDB bindings and RCA evidence, never high-volume traces.
5. Existing RCA agents use evidence references, rather than granting direct unrestricted OpenSearch access.

## Tenant boundary

Internal-only API key and trusted identity gateway as short-term development mechanism; OpenSearch document level security, scoped index permissions, signed service identity and systematic cross-tenant tests are required for production.

## Future integrations

- OTel Collector + Data Prepper pipelines (pinned upstream version, mapping checks).
- Topology Sync Worker: reconcile observed edges with existing CMDB, retaining provenance.
- Outbox Relay: SKIP LOCKED, retries, dead-letter table and downstream correlation adapter.
- Agent Tool Gateway: scoped templates, query cost and time limits, audit and redaction.
- PromQL: query-builder or per-tenant metrics backend; **never expose arbitrary expressions**.
- Production migrations with Alembic; production TLS, OpenSearch Security, snapshots.
- Shadow-mode evidence collection; per-tenant flags; safe rollback and replay tests.

## POC limitations

- Single-node optional OpenSearch profile uses insecure development settings; no public exposure.
- Database bootstrap uses create_all; only for a fresh disposable database.
- Outbox events are recorded but not yet dispatched.
- OpenSearch sample index requires a separately verified tenant-aware ingest pipeline and mapping.
- No claim is made that anomaly detection, RCA or autonomous remediation is finished.
