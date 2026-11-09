#!/bin/sh
# Read-only runtime audit for a *running* Compose project. No sudo, no installation.
set -eu
: "${GAMMA_HOME:?Set GAMMA_HOME}"
sh deploy/scripts/check-rootless-home.sh
project="${COMPOSE_PROJECT_NAME:-aiops-gamma}"
export COMPOSE_PROJECT_NAME="$project"
files="-f docker-compose.yml -f deploy/compose/compose.yaml -f deploy/compose/compose.rootless.yaml"
# shellcheck disable=SC2086
ids=$(docker compose $files ps --all -q)
[ -n "$ids" ] || { echo "No Compose containers to audit" >&2; exit 2; }
failed=0
for id in $ids; do
  name=$(docker inspect --format '{{.Name}}' "$id")
  running=$(docker inspect --format '{{.State.Running}}' "$id")
  privileged=$(docker inspect --format '{{.HostConfig.Privileged}}' "$id")
  user=$(docker inspect --format '{{.Config.User}}' "$id")
  [ "$running" = true ] || { echo "NOT RUNNING: $name" >&2; failed=1; }
  [ "$privileged" = false ] || { echo "PRIVILEGED: $name" >&2; failed=1; }
  [ -n "$user" ] && [ "$user" != 0 ] && [ "$user" != root ] || {
    echo "UNQUALIFIED CONFIG USER: $name ($user) — inspect image runtime UID" >&2; failed=1;
  }
  mounts=$(docker inspect --format '{{range .Mounts}}{{if eq .Type "bind"}}{{.Source}}{{println}}{{else}}NAMED_VOLUME{{println}}{{end}}{{end}}' "$id")
  oldifs=$IFS
  IFS='
'
  for mount in $mounts; do
    case "$mount" in
      "$GAMMA_HOME"/data/*) ;;
      NAMED_VOLUME) echo "NAMED VOLUME: $name" >&2; failed=1 ;;
      *) echo "OUT-OF-TREE BIND: $name $mount" >&2; failed=1 ;;
    esac
  done
  IFS=$oldifs
  echo "Audited $name (configured user=$user)"
done
[ "$failed" -eq 0 ] || { echo "Rootless Compose audit FAILED" >&2; exit 1; }
echo "Rootless Compose runtime configuration audit PASSED (does not prove no hidden writes or all services healthy)"
