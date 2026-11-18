-- Read-only preflight for PostgreSQL 16, including existing volumes.
-- Run as a trusted administrator against the application database:
-- psql -X -v ON_ERROR_STOP=1 -d aiops -f postgres/preflight/01-app-role.sql
\set ON_ERROR_STOP on
BEGIN TRANSACTION READ ONLY;
DO $preflight$
DECLARE
    app_role pg_catalog.pg_roles%ROWTYPE;
    privileged_roles text;
BEGIN
    SELECT * INTO app_role
    FROM pg_catalog.pg_roles
    WHERE rolname = 'gamma_app';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Preflight failed: gamma_app does not exist';
    END IF;

    IF NOT app_role.rolcanlogin OR app_role.rolsuper OR
       app_role.rolbypassrls OR app_role.rolcreatedb OR
       app_role.rolcreaterole OR app_role.rolreplication THEN
        RAISE EXCEPTION 'Preflight failed: unsafe gamma_app attributes';
    END IF;

    -- Conservatively traverse every membership edge, regardless of
    -- INHERIT or SET options, including nested and ADMIN-only memberships.
    WITH RECURSIVE reachable(roleid) AS (
        SELECT m.roleid
        FROM pg_catalog.pg_auth_members m
        WHERE m.member = app_role.oid
        UNION
        SELECT m.roleid
        FROM pg_catalog.pg_auth_members m
        JOIN reachable r ON m.member = r.roleid
    )
    SELECT string_agg(r.rolname::text, ', ' ORDER BY r.rolname)
    INTO privileged_roles
    FROM reachable x
    JOIN pg_catalog.pg_roles r ON r.oid = x.roleid
    WHERE r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR
          r.rolcreaterole OR r.rolreplication OR
          r.rolname = 'aiops' OR left(r.rolname, 3) = 'pg_';

    IF privileged_roles IS NOT NULL THEN
        RAISE EXCEPTION 'Preflight failed: privileged role memberships: %', privileged_roles;
    END IF;
END
$preflight$;
ROLLBACK;
\echo PostgreSQL application role preflight passed
-- Scope: role attributes and membership graph only. Object ownership,
-- ACLs, SECURITY DEFINER functions, RLS policies and credentials require
-- separate qualification. This script does not repair existing volumes.
