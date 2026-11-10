#!/bin/sh
# Read-only evidence capture for a disposable rootless GAMMA qualification host.
# Does not start/stop containers, alter permissions, or print secrets.
set -eu
: "${GAMMA_HOME:?Set GAMMA_HOME to an absolute path}"
sh deploy/scripts/check-rootless-home.sh
echo "Rootless daemon and data-root preflight: PASS"
echo "Host UID/GID: $(id -u):$(id -g)"
echo "GAMMA_HOME: $GAMMA_HOME"
for dir in "$GAMMA_HOME/data" "$GAMMA_HOME/data/postgres" "$GAMMA_HOME/data/opensearch"; do
  if [ -d "$dir" ]; then
    canonical=$(cd "$dir" && pwd -P)
    echo "Directory: $dir -> $canonical"
    stat -c '  owner=%u:%g mode=%a' "$dir"
  else
    echo "Directory missing: $dir"
  fi
done
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-aiops-gamma-rootless-smoke}"
ids=$(docker compose -f docker-compose.yml -f deploy/compose/compose.yaml -f deploy/compose/compose.rootless.yaml ps --all -q)
if [ -z "$ids" ]; then
  echo "No containers found for project $COMPOSE_PROJECT_NAME" >&2
  exit 2
fi
for id in $ids; do
  echo "Container: $(docker inspect --format '{{.Name}}' "$id")"
  docker inspect --format '  running={{.State.Running}} privileged={{.HostConfig.Privileged}} configured_user={{.Config.User}}' "$id"
  if [ "$(docker inspect --format '{{.State.Running}}' "$id")" = true ]; then
    if uid=$(docker exec "$id" sh -c "awk '/^Uid:/ {print \$2}' /proc/1/status"); then
      echo "  pid1_uid=$uid"
    else
      echo "  pid1_uid=UNAVAILABLE"
    fi
  fi
  docker inspect --format '{{range .Mounts}}  mount_type={{.Type}} mount_source={{.Source}} mount_destination={{.Destination}}{{println}}{{end}}' "$id"
done
echo "Evidence collection complete; run audit-rootless-compose.sh separately for the strict pass/fail decision."
