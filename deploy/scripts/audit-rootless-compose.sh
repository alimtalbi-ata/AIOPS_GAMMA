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
    echo "UNQUALIFIED CONFIG USER: $name ($user) — explicit non-root image user required" >&2; failed=1;
  }
  # Config.User and the running process UID are independent security facts.
  # Collect both; never treat a non-root process as a waiver for root config.
  if [ "$running" = true ]; then
    runtime_uid=$(docker exec "$id" sh -c "awk '/^Uid:/ {print \$2}' /proc/1/status") || {
      echo "RUNTIME UID UNAVAILABLE: $name" >&2
      failed=1
      runtime_uid=
    }
    case "$runtime_uid" in
      ''|*[!0-9]*) echo "INVALID RUNTIME UID: $name ($runtime_uid)" >&2; failed=1 ;;
      0) echo "ROOT RUNTIME UID: $name" >&2; failed=1 ;;
      *) echo "Runtime PID 1 UID: $name ($runtime_uid)" ;;
    esac
  fi
  mounts=$(docker inspect --format '{{range .Mounts}}{{if eq .Type "bind"}}{{.Source}}{{println}}{{else}}NAMED_VOLUME{{println}}{{end}}{{end}}' "$id")
  oldifs=$IFS
  IFS='
'
  for mount in $mounts; do
    case "$mount" in
      "$GAMMA_HOME"/data/*)
        # A lexical prefix is insufficient: a bind source may traverse a
        # symlink and resolve outside the user-owned installation directory.
        if [ ! -d "$mount" ]; then
          echo "BIND SOURCE NOT DIRECTORY: $name $mount" >&2
          failed=1
        else
          canonical=$(cd "$mount" && pwd -P) || {
            echo "BIND SOURCE UNRESOLVABLE: $name $mount" >&2
            failed=1
            canonical=
          }
          case "$canonical" in
            "$GAMMA_HOME"/data/*) ;;
            *) echo "BIND ESCAPES DATA ROOT: $name $mount -> $canonical" >&2; failed=1 ;;
          esac
        fi
        ;;
      NAMED_VOLUME) echo "NAMED VOLUME: $name" >&2; failed=1 ;;
      *) echo "OUT-OF-TREE BIND: $name $mount" >&2; failed=1 ;;
    esac
  done
  IFS=$oldifs
  echo "Audited $name (configured user=$user)"
done
[ "$failed" -eq 0 ] || { echo "Rootless Compose audit FAILED" >&2; exit 1; }
echo "Rootless Compose runtime configuration audit PASSED (does not prove no hidden writes or all services healthy)"
