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

## Runtime audit (rootless host required)

On a dedicated host with a configured rootless Docker daemon whose data-root is `$GAMMA_HOME/docker-data`, first validate the optional profiles explicitly:

```bash
export GAMMA_HOME="$HOME/aiops-gamma"
export COMPOSE_PROJECT_NAME=aiops-gamma
sh deploy/scripts/check-rootless-home.sh
# Rootless runtime smoke test must be done on a qualified disposable host.
# After starting the approved Compose services:
sh deploy/scripts/audit-rootless-compose.sh
```

The runtime audit is read-only and checks actual running container configuration, mounts and privileged mode; it intentionally **fails** if a service uses an unspecified/root-configured user or named volumes. PostgreSQL/OpenSearch upstream UID compatibility and filesystem ownership must be remediated rather than bypassing the audit. The audit does not assert network isolation, health or absence of writes to container-internal paths.

The earlier static CI check initially failed because `opensearch` was excluded by its `observability-demo` profile. CI now explicitly enables `relay` and `observability-demo` when asserting their rendered service configuration.

## Opt-in baseline rootless smoke (disposable host only)

The last static deployment workflow and Python workflow both passed on commit `ff995e86`. A new **manual**, non-destructive smoke script is available: `deploy/scripts/smoke-rootless.sh`. It checks the rootless engine/data-root, prepares only `GAMMA_HOME/data` directories, starts the core Compose UI/API/PostgreSQL services, probes the local UI over HTTP, and invokes the runtime mount/privilege audit. It **does not** install Docker or change system directories, and it intentionally leaves containers running for inspection. Set real local secrets in the environment first.

```bash
export GAMMA_HOME="$HOME/aiops-gamma"
export POSTGRES_PASSWORD='set-a-strong-test-password'
export INTERNAL_API_KEY='set-a-strong-test-api-key'
sh deploy/scripts/smoke-rootless.sh
```

**Expected unresolved gate:** upstream PostgreSQL's image may declare an empty/root config user even when its entrypoint drops privileges, so the strict runtime audit may fail until its image/UID and init permissions are qualified. OpenSearch is not started by this baseline script. The test has **not** been run on an actual rootless host by this change; treat any result as unverified until executed and logged.

## Additional rootless safeguards

The rootless preflight now checks the directory owner and rejects existing symlinked data paths escaping `GAMMA_HOME`. The runtime audit includes stopped containers (`docker compose ps --all`) rather than silently ignoring them. CI runs mocked-Docker preflight tests for canonical roots and symlink escapes; these tests do not require or emulate a real Docker daemon.

## UI container runtime smoke in CI

The deployment workflow now builds and **starts** the non-root UI container with `--cap-drop ALL`, `--security-opt no-new-privileges`, UID/GID `101:101`, and a localhost-only published port `18080:8080`. It polls the HTTP homepage, verifies an HTML response, confirms the container remains running, and inspects the configured user/privileged flag. The container is removed after the test. This uses the **GitHub-hosted Docker daemon**, not a certified rootless daemon, and does not exercise the complete stack.
