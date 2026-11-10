#!/bin/sh
# Opt-in smoke test on a disposable, user-owned Docker Engine rootless host.
# No sudo, package installation, or system directory writes.
set -eu
: "${GAMMA_HOME:?Set GAMMA_HOME to an absolute path}"
: "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}"
: "${INTERNAL_API_KEY:?Set INTERNAL_API_KEY}"
sh deploy/scripts/check-rootless-home.sh
# This smoke is only for a fresh disposable installation. Refuse to run on
# existing PostgreSQL data even if the caller explicitly opts in.
[ "${GAMMA_ROOTLESS_SMOKE_DISPOSABLE:-}" = "YES" ] || {
  echo "Set GAMMA_ROOTLESS_SMOKE_DISPOSABLE=YES for a dedicated disposable host" >&2
  exit 2
}
if [ -d "$GAMMA_HOME/data/postgres" ] && [ -n "$(ls -A "$GAMMA_HOME/data/postgres")" ]; then
  echo "Refusing rootless smoke: PostgreSQL data directory is not empty" >&2
  exit 2
fi
for dir in "$GAMMA_HOME/data/postgres" "$GAMMA_HOME/data/opensearch"; do
  if [ ! -d "$dir" ]; then
    (umask 077; mkdir -p "$dir")
  fi
done
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-aiops-gamma-rootless-smoke}"
# A fresh local data directory does not imply a fresh Compose project.
# Fail before any 'up' if this project already has containers (running or
# stopped). Never replace another project's containers during qualification.
existing=$(docker compose -f docker-compose.yml -f deploy/compose/compose.yaml -f deploy/compose/compose.rootless.yaml ps --all -q) || {
  echo "Unable to inspect existing Compose project; refusing smoke" >&2
  exit 2
}
[ -z "$existing" ] || {
  echo "Refusing rootless smoke: Compose project $COMPOSE_PROJECT_NAME already has containers" >&2
  exit 2
}
command -v python3 >/dev/null 2>&1 || { echo "python3 required for port collision preflight" >&2; exit 2; }
python3 deploy/scripts/check-smoke-ports.py || exit 2
echo "Using fresh project $COMPOSE_PROJECT_NAME; cleanup is manual to preserve evidence."
# Never enable optional relay or insecure observability demo for the baseline smoke.
docker compose -f docker-compose.yml -f deploy/compose/compose.yaml -f deploy/compose/compose.rootless.yaml config --format json | python3 deploy/scripts/check-postgres-rootless.py
docker compose -f docker-compose.yml -f deploy/compose/compose.yaml -f deploy/compose/compose.rootless.yaml up -d --build --wait frontend api postgres
docker compose -f docker-compose.yml -f deploy/compose/compose.yaml -f deploy/compose/compose.rootless.yaml ps
# --wait does not prove HTTP readiness for services without healthchecks.
# Require curl rather than silently skipping the core runtime assertion.
command -v curl >/dev/null 2>&1 || {
  echo "curl required for rootless HTTP smoke; refusing to skip" >&2
  exit 2
}
for url in http://127.0.0.1:5173/ http://127.0.0.1:8000/api/v1/health/live; do
  ready=0
  i=0
  while [ "$i" -lt 30 ]; do
    if curl --fail --silent --max-time 3 "$url" -o /dev/null; then
      ready=1
      break
    fi
    i=$((i + 1))
    sleep 2
  done
  [ "$ready" -eq 1 ] || {
    echo "Rootless HTTP readiness failed: $url" >&2
    exit 1
  }
done
docker compose -f docker-compose.yml -f deploy/compose/compose.yaml -f deploy/compose/compose.rootless.yaml exec -T postgres pg_isready -U aiops -d aiops
# The audit is intentionally strict about configured image users. Upstream
# PostgreSQL may fail this gate despite dropping privileges at runtime.
sh deploy/scripts/audit-rootless-compose.sh
echo "Rootless baseline smoke completed. Manually inspect logs and remove the project when finished."
