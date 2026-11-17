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
  # Audit the running container, not only the merged Compose declaration.
  cap_add=$(docker inspect --format '{{json .HostConfig.CapAdd}}' "$id") || { echo "CAP_ADD UNAVAILABLE: $name" >&2; failed=1; cap_add=unknown; }
  cap_drop=$(docker inspect --format '{{json .HostConfig.CapDrop}}' "$id") || { echo "CAP_DROP UNAVAILABLE: $name" >&2; failed=1; cap_drop=unknown; }
  case "$cap_add" in
    null|\[\]) ;;
    *) echo "ADDED CAPABILITIES: $name ($cap_add)" >&2; failed=1 ;;
  esac
  case "$cap_drop" in
    '["ALL"]'|'["all"]') ;;
    *) echo "CAPABILITIES NOT DROPPED: $name ($cap_drop)" >&2; failed=1 ;;
  esac
  [ "$running" = true ] || { echo "NOT RUNNING: $name" >&2; failed=1; }
  [ "$privileged" = false ] || { echo "PRIVILEGED: $name" >&2; failed=1; }
  # Docker accepts UID, UID:GID and user-name forms. A numeric UID 0
  # remains root even with a nonzero GID (0:1000, 00:1000, etc.).
  configured_uid=${user%%:*}
  case "$user" in
    *:*:*) echo "UNQUALIFIED CONFIG USER: $name ($user) — multiple colons" >&2; failed=1 ;;
    *:*)
      configured_gid=${user#*:}
      case "$configured_gid" in
        ''|*[!0-9]*) echo "UNQUALIFIED CONFIG USER: $name ($user) — numeric GID required" >&2; failed=1 ;;
      esac
      ;;
  esac
  case "$configured_uid" in
    ''|root|*[!0-9]*)
      # Non-numeric user names cannot be proven non-root from Config.User
      # alone. Fail closed until a numeric UID is explicitly configured.
      echo "UNQUALIFIED CONFIG USER: $name ($user) — numeric non-root UID required" >&2
      failed=1
      ;;
    *)
      # Strip zero digits without shell arithmetic (which may treat 08 as
      # invalid octal on some POSIX shells).
      nonzero_digits=$(printf '%s' "$configured_uid" | tr -d 0)
      if [ -z "$nonzero_digits" ]; then
        echo "UNQUALIFIED CONFIG USER: $name ($user) — root UID" >&2
        failed=1
      fi
      ;;
  esac
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
      *)
        runtime_nonzero=$(printf '%s' "$runtime_uid" | tr -d 0)
        if [ -z "$runtime_nonzero" ]; then
          echo "ROOT RUNTIME UID: $name ($runtime_uid)" >&2
          failed=1
        else
          echo "Runtime PID 1 UID: $name ($runtime_uid)"
        fi
        ;;
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
            "$GAMMA_HOME"/data/*)
              # Docker rootless bind sources must be owned by the invoking
              # user; group/world-writable sources are rejected. Postgres
              # may change ownership *inside* the user namespace, so this
              # remains a deliberately strict host-side acceptance gate.
              owner=$(stat -c %u "$canonical") || { echo "BIND OWNER UNKNOWN: $name $canonical" >&2; failed=1; owner=; }
              mode=$(stat -c %a "$canonical") || { echo "BIND MODE UNKNOWN: $name $canonical" >&2; failed=1; mode=; }
              [ "$owner" = "$(id -u)" ] || { echo "BIND NOT USER OWNED: $name $canonical (uid=$owner)" >&2; failed=1; }
              # GNU stat octal permission bits; ignore special bits here,
              # reject any group/other write bit in the low three digits.
              case "$mode" in
                *[2367][0-7]|*[0-7][2367]) echo "BIND GROUP/OTHER WRITABLE: $name $canonical (mode=$mode)" >&2; failed=1 ;;
              esac
              ;;
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
