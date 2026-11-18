-- Post-migration read-only qualification; not a repair or complete ACL proof.
\set ON_ERROR_STOP on
BEGIN TRANSACTION READ ONLY;
DO $audit$
DECLARE
    t text;
    obj pg_catalog.pg_class%ROWTYPE;
    worker pg_catalog.pg_roles%ROWTYPE;
BEGIN
    SELECT * INTO worker FROM pg_catalog.pg_roles WHERE rolname = 'gamma_outbox_worker';
    IF NOT FOUND OR worker.rolcanlogin OR worker.rolsuper OR worker.rolbypassrls OR
       worker.rolcreatedb OR worker.rolcreaterole OR worker.rolreplication THEN
        RAISE EXCEPTION 'Schema audit: unsafe worker role attributes';
    END IF;
    IF EXISTS (
        WITH RECURSIVE reachable(roleid) AS (
            SELECT roleid FROM pg_catalog.pg_auth_members WHERE member = worker.oid
            UNION
            SELECT m.roleid FROM pg_catalog.pg_auth_members m JOIN reachable r ON m.member = r.roleid
        )
        SELECT 1 FROM reachable x JOIN pg_catalog.pg_roles r ON r.oid = x.roleid
        WHERE r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication
           OR r.rolname IN ('aiops', 'gamma_app') OR left(r.rolname, 3) = 'pg_'
    ) OR pg_has_role('gamma_app', 'gamma_outbox_worker', 'MEMBER') THEN
        RAISE EXCEPTION 'Schema audit: unsafe worker role memberships';
    END IF;
    FOREACH t IN ARRAY ARRAY['integration_inbox','integration_outbox','telemetry_service_bindings','investigation_evidence']
    LOOP
        SELECT * INTO obj FROM pg_catalog.pg_class WHERE oid = to_regclass('public.' || t);
        IF NOT FOUND OR obj.relkind <> 'r' OR NOT obj.relrowsecurity OR NOT obj.relforcerowsecurity THEN
            RAISE EXCEPTION 'Schema audit: missing table or forced RLS: %', t;
        END IF;
        IF pg_has_role('gamma_app', obj.relowner, 'MEMBER') OR
           pg_has_role('gamma_outbox_worker', obj.relowner, 'MEMBER') THEN
            RAISE EXCEPTION 'Schema audit: runtime role reaches table owner: %', t;
        END IF;
        IF has_table_privilege('gamma_app', obj.oid, 'TRUNCATE') OR
           has_table_privilege('gamma_app', obj.oid, 'TRIGGER') OR
           has_table_privilege('gamma_outbox_worker', obj.oid, 'TRUNCATE') THEN
            RAISE EXCEPTION 'Schema audit: unsafe table privilege: %', t;
        END IF;
        -- PG16 policy contract: pin role scope, command, permissiveness,
        -- and the deparsed predicate. No additional policy may widen access.
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_policy p
            WHERE p.polrelid = obj.oid AND p.polname = 'tenant_isolation'
              AND p.polcmd = '*' AND p.polpermissive
              AND p.polroles = CASE WHEN t = 'integration_outbox'
                    THEN ARRAY['gamma_app'::regrole::oid] ELSE ARRAY[0::oid] END
              AND pg_get_expr(p.polqual, p.polrelid) =
                  '(tenant_id = (NULLIF(current_setting(''app.tenant_id''::text, true), ''''::text))::uuid)'
              AND pg_get_expr(p.polwithcheck, p.polrelid) =
                  '(tenant_id = (NULLIF(current_setting(''app.tenant_id''::text, true), ''''::text))::uuid)'
        ) THEN
            RAISE EXCEPTION 'Schema audit: tenant policy drift: %', t;
        END IF;
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_policy p WHERE p.polrelid = obj.oid
              AND p.polname <> 'tenant_isolation'
              AND NOT (t = 'integration_outbox' AND p.polname IN
                  ('worker_access','worker_identity','worker_role_separation'))
        ) THEN
            RAISE EXCEPTION 'Schema audit: unexpected policy: %', t;
        END IF;
        IF t = 'integration_outbox' AND (
            SELECT count(*) FROM pg_catalog.pg_policy p WHERE p.polrelid = obj.oid
            AND ((p.polname = 'worker_access' AND p.polpermissive
                  AND p.polroles = ARRAY['gamma_outbox_worker'::regrole::oid])
              OR (p.polname = 'worker_identity' AND NOT p.polpermissive
                  AND p.polroles = ARRAY['gamma_outbox_worker'::regrole::oid])
              OR (p.polname = 'worker_role_separation' AND NOT p.polpermissive
                  AND p.polroles = ARRAY[0::oid]))
            AND p.polcmd = '*' AND p.polqual IS NOT NULL AND p.polwithcheck IS NOT NULL
        ) <> 3 THEN
            RAISE EXCEPTION 'Schema audit: worker policy structure drift';
        END IF;
    END LOOP;
    SELECT * INTO obj FROM pg_catalog.pg_class
    WHERE oid = to_regclass('public.outbox_worker_identity');
    IF NOT FOUND OR obj.relkind <> 'r' OR NOT obj.relrowsecurity THEN
        RAISE EXCEPTION 'Schema audit: worker identity table missing or RLS disabled';
    END IF;
    IF pg_has_role('gamma_app', obj.relowner, 'MEMBER') OR
       pg_has_role('gamma_outbox_worker', obj.relowner, 'MEMBER') THEN
        RAISE EXCEPTION 'Schema audit: runtime role reaches worker identity owner';
    END IF;
    IF (SELECT count(*) FROM pg_catalog.pg_policy WHERE polrelid = obj.oid) <> 1
       OR NOT EXISTS (
           SELECT 1 FROM pg_catalog.pg_policy p
           WHERE p.polrelid = obj.oid AND p.polname = 'worker_self'
             AND p.polcmd = 'r' AND p.polpermissive
             AND p.polroles = ARRAY[worker.oid]
             AND pg_get_expr(p.polqual, p.polrelid) = '(login_name = SESSION_USER)'
             AND p.polwithcheck IS NULL
       ) THEN
        RAISE EXCEPTION 'Schema audit: worker identity policy drift';
    END IF;
    IF has_any_column_privilege('gamma_app', obj.oid, 'SELECT,INSERT,UPDATE,REFERENCES')
       OR has_table_privilege('gamma_app', obj.oid, 'DELETE,TRUNCATE,TRIGGER')
       OR has_any_column_privilege('gamma_outbox_worker', obj.oid, 'INSERT,UPDATE,REFERENCES')
       OR has_table_privilege('gamma_outbox_worker', obj.oid, 'DELETE,TRUNCATE,TRIGGER')
       OR NOT has_table_privilege('gamma_outbox_worker', obj.oid, 'SELECT') THEN
        RAISE EXCEPTION 'Schema audit: unsafe worker identity privileges';
    END IF;
    IF has_schema_privilege('gamma_app', 'public', 'CREATE') OR
       has_schema_privilege('gamma_outbox_worker', 'public', 'CREATE') THEN
        RAISE EXCEPTION 'Schema audit: runtime role can create public objects';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.prosecdef
          AND (has_function_privilege('gamma_app', p.oid, 'EXECUTE')
            OR has_function_privilege('gamma_outbox_worker', p.oid, 'EXECUTE'))
    ) THEN
        RAISE EXCEPTION 'Schema audit: executable public SECURITY DEFINER routine';
    END IF;
END
$audit$;
ROLLBACK;
\echo PostgreSQL schema security audit passed
-- The pinned tenant expression is PG16-specific; worker predicate semantics,
-- complete ACL review and behavioral isolation still require separate evidence.
