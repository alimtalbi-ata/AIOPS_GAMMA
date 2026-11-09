# GAMMA deployment skeleton (increment 1)

The **existing** root `docker-compose.yml` already starts GAMMA UI, API and PostgreSQL. This increment adds a Compose security override and a Helm chart for **UI + API only**. It does not claim to deploy every upstream dependency or to be production-qualified.

## Compose (local)

```bash
cp deploy/compose/.env.example .env
# Replace both placeholder credentials before starting.
docker compose --env-file .env -f docker-compose.yml -f deploy/compose/compose.yaml config
docker compose --env-file .env -f docker-compose.yml -f deploy/compose/compose.yaml up -d --build
```

The override keeps GLPI/canonical reads disabled and does not enable the optional observability profile. The existing PostgreSQL named volume is used. Do not expose this stack directly to the Internet.

## Helm (Kubernetes staging skeleton)

Build and push the root Dockerfile and `frontend/Dockerfile` as immutable OCI images. Set `api.image` and `ui.image` to pinned digests. Provision **externally** an authorized PostgreSQL endpoint and two Secrets:

- `gamma-api-credentials` with key `internal-api-key`
- `gamma-database` with key `url` (SQLAlchemy asyncpg DSN)

```bash
helm lint deploy/helm/gamma
helm template gamma deploy/helm/gamma --namespace gamma
helm upgrade --install gamma deploy/helm/gamma -n gamma --create-namespace \
  --set-string api.image='registry.example/gamma-api@sha256:...' \
  --set-string ui.image='registry.example/gamma-ui@sha256:...'
```

Do not use the placeholder digest values above literally. Ingress is disabled by default. The chart installs ingress isolation policies but **does not** establish complete egress isolation, TLS, OIDC, database lifecycle, backups, migrations, autoscaling, or production readiness. UI's existing Nginx proxy config must be checked against the Kubernetes API service DNS before deployment. Health probes are TCP-only until dedicated readiness checks are qualified.

## Scope and next integration gates

- Existing upstream stacks (`aiops`, `observability-stack`, `sentinel-llm`, `arguslm-llm`, chosen investigator) need pinned image/Helm/Compose integration **individually**. No mock services are labeled live.
- Do not expose `X-Internal-Api-Key` to a browser; add a server-side authenticated gateway before exposing API.
- CI should lint Helm and validate Compose config. Real Compose smoke tests and Kubernetes staging tests remain separate required gates.
- Keep PR draft; no LIVE remediation or GLPI writes.
