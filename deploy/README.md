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

## PostgreSQL + API CI runtime integration

A separate GitHub Actions job now starts `postgres` and `api` using the standard Compose files, waits for PostgreSQL health, probes `GET /api/v1/health/live` on loopback, checks the API container's configured non-root user and non-privileged mode, and collects logs/tears down the test stack even after failure. It uses disposable CI-only credentials and removes test volumes. **This is a runtime integration test on the GitHub-hosted Docker daemon, not Docker rootless.** It does not prove DB migrations, tenant authorization, persistence across restarts or host-path confinement.

## Single-directory bind-mount runtime regression

A new GitHub-hosted CI job starts the **UI + API + PostgreSQL** baseline with the rootless Compose overlay and a real PostgreSQL bind mount under the runner's `GAMMA_HOME/data/postgres`. It probes both HTTP endpoints, checks PostgreSQL readiness, inspects the actual mounted host path, and retains filesystem evidence rather than force-deleting it on failure. This detects many UID/mount errors, but **the GitHub-hosted Docker daemon is not rootless**, and the job does not enforce the strict `check-rootless-home.sh` preflight. It does not qualify OpenSearch, host filesystem confinement or Kubernetes.

## PostgreSQL initialization capabilities

The first bind-mounted baseline runtime CI run failed: upstream `postgres:16-alpine` needs to `chmod` and `chown` its fresh data directory and runtime socket directory before dropping to the PostgreSQL account. The rootless overlay now retains `cap_drop: [ALL]` but adds `CHOWN`, `FOWNER`, and `DAC_OVERRIDE` **only for PostgreSQL**. On a verified rootless Docker daemon these are namespaced capabilities, not host-root privileges. This is a compatibility exception, not a claim of fully non-root PostgreSQL initialization. Validate actual runtime UID, bind ownership and host containment on a dedicated rootless host before production.

### PostgreSQL UID transition

A subsequent CI run got past filesystem setup but PostgreSQL failed with `failed switching to 'postgres': operation not permitted`. The upstream entrypoint also requires `SETUID` and `SETGID` to drop from its initialization account to the postgres account. The rootless overlay now grants those two capabilities **only to PostgreSQL**, in addition to `CHOWN`, `FOWNER` and `DAC_OVERRIDE`. These permissions are container-scoped and must be assessed against a verified rootless engine before acceptance; the CI runtime runner is not rootless.

## PostgreSQL bind persistence regression

The `single-directory-runtime` CI job now writes a sentinel record to PostgreSQL, stops and removes **only the PostgreSQL container**, recreates it against the same `GAMMA_HOME/data/postgres` bind mount, and verifies that the record and the expected mount path survive. This is a container-recreation durability smoke, not a backup/restore test or a crash-consistency guarantee. It still runs on the GitHub-hosted Docker daemon, **not rootless**.

## CI-only PostgreSQL logical backup/restore rehearsal

After verifying bind-mount persistence, the `single-directory-runtime` job writes a logical `pg_dump` to `$GAMMA_HOME/backups/ci-postgres.sql` (directory mode 0700, file mode 0600), checks file ownership, **drops only its disposable CI sentinel table**, restores the dump through `psql -v ON_ERROR_STOP=1`, and verifies the restored record. This destructive rehearsal is CI-only: do **not** copy the DROP TABLE step into a production runbook. A successful CI result does not yet demonstrate point-in-time recovery, encrypted/off-host backups, retention, disaster recovery, or actual rootless-engine operation.

## Strict rootless smoke readiness gates

The opt-in `deploy/scripts/smoke-rootless.sh` now **requires** `curl`, retries both UI and API HTTP probes (up to roughly 60 seconds each), and checks PostgreSQL readiness before invoking the strict runtime audit. It never silently skips HTTP validation. The upstream PostgreSQL image may still fail the audit because its configured container user is empty/root even though its entrypoint drops to `postgres` at runtime; do not bypass that failure or claim full rootless compliance without a qualified image/runtime UID design. The successful GitHub-hosted logical backup/restore job does not use a rootless Docker daemon.

## Rootless runtime identity evidence

The opt-in rootless audit now inspects **both** the image/container configured user (`docker inspect .Config.User`) and the running PID 1 UID from `/proc/1/status` via `docker exec`. It fails closed if the process UID cannot be read, is invalid or zero; it also **continues to reject** an empty/root configured user even when PID 1 is non-root. This makes the upstream PostgreSQL identity mismatch visible instead of treating runtime privilege dropping as proof of a compliant non-root image. This audit is only run on a dedicated rootless host, not the GitHub-hosted Docker CI runner.
