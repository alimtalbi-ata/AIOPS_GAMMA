#!/bin/sh
# Preflight only: never installs packages or modifies system paths.
set -eu
: "${GAMMA_HOME:?Set GAMMA_HOME to an absolute, user-owned directory}"
case "$GAMMA_HOME" in
  /*) ;;
  *) echo "GAMMA_HOME must be absolute" >&2; exit 2 ;;
esac
case "$GAMMA_HOME" in
  /|/bin|/bin/*|/sbin|/sbin/*|/var|/var/*|/tmp|/tmp/*|/usr|/usr/*|/etc|/etc/*|/proc|/proc/*|/sys|/sys/*|/dev|/dev/*)
    echo "Refusing system directory GAMMA_HOME" >&2; exit 2 ;;
esac
[ -d "$GAMMA_HOME" ] || { echo "Create GAMMA_HOME as your user before running" >&2; exit 2; }
[ -w "$GAMMA_HOME" ] || { echo "GAMMA_HOME is not writable" >&2; exit 2; }
resolved=$(cd "$GAMMA_HOME" && pwd -P)
[ "$resolved" = "$GAMMA_HOME" ] || { echo "GAMMA_HOME must be canonical (no symlinks or ..)" >&2; exit 2; }
command -v docker >/dev/null 2>&1 || { echo "Docker CLI missing" >&2; exit 2; }
docker info --format '{{json .SecurityOptions}}' | grep -q rootless || {
  echo "Docker daemon is not confirmed rootless; refusing" >&2
  exit 2
}
echo "Rootless daemon detected; directory preflight passed."
echo "Still verify Docker data-root, per-image UID ownership and all bind mounts before starting."
