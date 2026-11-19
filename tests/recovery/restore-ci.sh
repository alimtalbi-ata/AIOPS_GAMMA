#!/usr/bin/env bash
set -euo pipefail
# CI only: source service is disposable and destination is a fresh cluster.
[[ "${GITHUB_ACTIONS:-}" == true && "${GAMMA_TEST_DISPOSABLE:-}" == 1 ]]
mkdir -p recovery-evidence
work=$(mktemp -d)
trap 'docker rm -f gamma-recovery-target >/dev/null 2>&1 || true; rm -rf "$work"' EXIT
source_id=$(docker ps --filter publish=5432 --format '{{.ID}}')
[[ $(wc -w <<< "$source_id") == 1 ]]
src() { docker exec -i "$source_id" "$@"; }
dst() { docker exec -i gamma-recovery-target "$@"; }
sql() { src psql -X -v ON_ERROR_STOP=1 -U gamma_admin -d gamma_test "$@"; }
sql -c "INSERT INTO gateway_assertion_replay VALUES (repeat('d',64),now()+interval '1 hour')"
src pg_dumpall -U gamma_admin --globals-only > "$work/globals.sql"
src pg_dump -U gamma_admin -Fc gamma_test > "$work/database.dump"
sha256sum "$work/database.dump" | cut -d ' ' -f1 > recovery-evidence/database.sha256
snapshot=$(date +%s)
sql -c "INSERT INTO gateway_assertion_replay VALUES (repeat('e',64),now()+interval '1 hour')"
# Simulate loss of writes after the snapshot, never touch a non-CI database.
start=$(date +%s)
docker run -d --name gamma-recovery-target -e POSTGRES_USER=recovery_bootstrap -e POSTGRES_PASSWORD=disposable_restore -e POSTGRES_DB=postgres postgres:16
for i in $(seq 1 60); do
  if dst pg_isready -U recovery_bootstrap -d postgres; then break; fi
  sleep 1
done
dst psql -X -v ON_ERROR_STOP=1 -U recovery_bootstrap -d postgres < "$work/globals.sql"
dst createdb -U recovery_bootstrap -O gamma_admin gamma_test
dst pg_restore --exit-on-error -U recovery_bootstrap -d gamma_test < "$work/database.dump"
dst psql -X -v ON_ERROR_STOP=1 -U gamma_admin -d gamma_test -At <<'SQL' > recovery-evidence/restored-checks.txt
SELECT version_num FROM alembic_version;
SELECT count(*) FROM gateway_assertion_replay WHERE assertion_digest=repeat('d',64);
SELECT count(*) FROM gateway_assertion_replay WHERE assertion_digest=repeat('e',64);
SQL
diff -u <(printf '0009_replay_bounded\n1\n0\n') recovery-evidence/restored-checks.txt
for gate in postgres/preflight/01-app-role.sql postgres/preflight/02-schema-security.sql; do
  docker exec -i -e PGPASSWORD=disposable_runtime gamma-recovery-target psql -X -h 127.0.0.1 -U gamma_app -d gamma_test -v ON_ERROR_STOP=1 < "$gate"
done
printf 'snapshot_epoch=%s\nrestore_elapsed_seconds=%s\npost_snapshot_write_missing=1\n' "$snapshot" "$(( $(date +%s)-start ))" > recovery-evidence/timing.txt
# Re-run original behavioral suite against restored cluster using the original host port.
# Export restored contents back into disposable source for behavioral rerun.
dst pg_dump -U gamma_admin -Fc gamma_test > "$work/restored.dump"
sql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='gamma_test' AND pid<>pg_backend_pid()"
src dropdb -U gamma_admin gamma_test
src createdb -U gamma_admin gamma_test
src pg_restore --exit-on-error -U gamma_admin -d gamma_test < "$work/restored.dump"
sql -c "TRUNCATE gateway_assertion_replay" 
