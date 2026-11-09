#!/bin/sh
# Opt-in smoke test on a disposable, user-owned Docker Engine rootless host.
# No sudo, package installation, or system directory writes.
set -eu
: "${GAMMA_HOME:?Set GAMMA_HOME to an absolute path}"
: "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}"
: "${INTERNAL_API_KEY:?Set INTERNAL_API_KEY}"
sh deploy/scripts/check-rootless-home.sh
for dir in "$GAMMA_HOME/data/postgres" "$GAMMA_HOME/data/opensearch"; do
  mkdir -p "$dir"
done
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-aiops-gamma-rootless-smoke}"
echo "Using project $COMPOSE_PROJECT_NAME; cleanup is manual to preserve evidence."
# Never enable optional relay or insecure observability demo for the baseline smoke.
docker compose -f docker-compose.yml -f deploy/compose/compose.yaml -f deploy/compose/compose.rootless.yaml config --quiet
docker compose -f docker-compose.yml -f deploy/compose/compose.yaml -f deploy/compose/compose.rootless.yaml up -d --build --wait frontend api postgres
docker compose -f docker-compose.yml -f deploy/compose/compose.yaml -f deploy/compose/compose.rootless.yaml ps
# Confirm actual HTTP response from the local UI. API auth is not exposed to browsers.
if command -v curl >/dev/null 2>&1; then
  curl --fail --silent --show-error --max-time 15 http://127.0.0.1:5173/ >/dev/null
else
  echo "curl not found; UI HTTP smoke skipped" >&2
fi
sh deploy/scripts/audit-rootless-compose.sh
echo "Rootless baseline smoke completed. Manually inspect logs and remove the project when finished."
