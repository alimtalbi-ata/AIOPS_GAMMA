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

## Single-directory rootless experiment (not yet qualified)

The optional `deploy/compose/compose.rootless.yaml` replaces PostgreSQL/OpenSearch named volumes with bind mounts under `$GAMMA_HOME/data` and adds privilege restrictions. **It is not sufficient alone**: upstream image UID, permissions, Docker daemon data-root and nginx non-root behavior need tests. The preflight script checks a canonical owned directory and detects a rootless daemon, but does not provision dependencies or modify the host.

```bash
export GAMMA_HOME="$HOME/aiops-gamma"
mkdir -p "$GAMMA_HOME/data/postgres" "$GAMMA_HOME/data/opensearch"
sh deploy/scripts/check-rootless-home.sh
# Only after preparing correct UID/GID and validating rootless Docker data-root:
docker compose -f docker-compose.yml -f deploy/compose/compose.yaml -f deploy/compose/compose.rootless.yaml config
```

Do not run `up` as proof of rootless compliance without checking the [rootless installation contract](../docs/ROOTLESS-SINGLE-DIRECTORY.md).

## Non-root UI increment

The UI now uses `nginxinc/nginx-unprivileged:1.27-alpine`, explicitly runs as UID/GID `101:101`, and listens on **8080** internally. The root Compose mapping is `127.0.0.1:5173:8080`; Helm's UI service also targets 8080 and declares a non-root pod security context. CI now builds the UI image, asserts its configured user, and runs `nginx -t` as UID 101 with dropped capabilities. The CI workflow also validates the rootless Compose overlay configuration and shell syntax.

The rootless preflight now **refuses** a Docker daemon whose `DockerRootDir` is outside `$GAMMA_HOME/docker-data`. It does not configure Docker for you. It must run against the intended rootless daemon; verify `DOCKER_HOST` and the context first. Full runtime smoke tests, bind-mount ownership, PostgreSQL/OpenSearch startup, read-only root filesystems and Kubernetes staging remain pending.

## Compose CI regression fix

The original CI failure was caused by duplicate `no-new-privileges:true` entries after merging `deploy/compose/compose.yaml` and `compose.rootless.yaml`. The rootless overlay now inherits this option from the base security overlay for API/frontend and adds only its own UID/capability/bind-mount settings. CI also inspects the rendered Compose JSON for expected bind mounts and UID values. **Static validation is not a live rootless runtime test.**
