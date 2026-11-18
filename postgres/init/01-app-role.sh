#!/bin/sh
set -eu
: "${APP_DB_USER:=gamma_app}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD must be set}"
[ "$APP_DB_USER" = gamma_app ] || { echo "Unsupported application role" >&2; exit 1; }
[ "$POSTGRES_USER" != "$APP_DB_USER" ] || { echo "Application and bootstrap roles must differ" >&2; exit 1; }
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=app_user="$APP_DB_USER" \
  --set=app_password="$APP_DB_PASSWORD" <<'SQL'
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION',
  :'app_user', :'app_password'
) WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT 1 / CASE WHEN count(*) = 1 AND bool_and(rolcanlogin AND NOT (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication)) THEN 1 ELSE 0 END
FROM pg_roles WHERE rolname = :'app_user';
SQL
