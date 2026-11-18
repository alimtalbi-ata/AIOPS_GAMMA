-- Post-migration read-only qualification; not a repair or complete ACL proof.
\set ON_ERROR_STOP on
BEGIN TRANSACTION READ ONLY;
DO $audit$
DECLARE
    t text;
    obj pg_catalog.pg_class%ROWTYPE;
BEGIN
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
