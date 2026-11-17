# AIOPS_GAMMA — developer and operations guide

## Developer startup
```bash
git clone https://github.com/alimtalbi-ata/AIOPS_GAMMA.git
cd AIOPS_GAMMA
git checkout feat/observability-foundation
cp .env.example .env
# Set a unique INTERNAL_API_KEY and review network/secret settings.
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose ps
```

Frontend demo: http://127.0.0.1:5173. All displayed sample telemetry is synthetic. Do not expose API or demo OpenSearch publicly. Consult README and docker-compose for exact service names, ports and optional profiles.

## Local verification
```bash
python -m pip install -e '.[test]'
pytest -q
python -m compileall -q app
cd frontend
npm install --no-audit --no-fund
npm run build
```

## Safe operation and troubleshooting
- Health: `GET /api/v1/health/live` reports process liveness, **not** upstream readiness or tenant authorization.
- If OpenSearch unavailable, leave `ENABLE_OPENSEARCH=false`; alert ingestion has its own flag.
- Metrics endpoint deliberately returns 501 until a tenant-safe query builder exists.
- Outbox relay requires separately configured downstream and operational supervision; inspect relay source before enabling.
- Never inject credentials, host-specific configuration, backups or production incident payloads into repository files, demo fixtures or LLM prompts.
- Do not run `app.init_db` on a production DB; use Alembic migrations with backup and rollback plan.
- Never activate LIVE remediation from policy preview; only the independently authorized existing Core/Policy/Temporal path may eventually perform effects.
- Production readiness requires gateway identity, RBAC/DLS, TLS, observability and fault-injection tests; this compose stack is development-only.

## PR acceptance checklist
1. Relevant issue linked and acceptance criteria explicit.
2. Unit/integration tests run and GitHub Actions HEAD green.
3. Tenant and security negative tests included for every new endpoint.
4. Feature flag and rollback instructions documented.
5. `docs/PROJECT-STATUS.md` and `docs/HANDOVER.md` updated.
6. Reviewer verifies source ownership and no unauthorized execution path.
