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
        IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_policy WHERE polrelid = obj.oid AND polname = 'tenant_isolation') THEN
            RAISE EXCEPTION 'Schema audit: missing tenant policy: %', t;
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
-- Policy presence does not prove predicate correctness or absence of other
-- permissive policies. Behavioral tenant tests and full ACL review remain required.
