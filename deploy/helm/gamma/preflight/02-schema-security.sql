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
    -- Relay remains HOLD: no individual worker identities may be provisioned
    -- until their full role graph and tenant bindings are separately qualified.
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members WHERE roleid = worker.oid) THEN
        RAISE EXCEPTION 'Schema audit: worker membership provisioning is on HOLD';
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
        IF t = 'integration_outbox' AND EXISTS (
            SELECT 1 FROM pg_catalog.pg_policy p
            WHERE p.polrelid = obj.oid
              AND p.polname IN ('worker_access','worker_identity','worker_role_separation')
              AND (
                  regexp_replace(pg_get_expr(p.polqual, p.polrelid), '[[:space:]]+', ' ', 'g')
                      IS DISTINCT FROM
                      CASE WHEN p.polname = 'worker_role_separation'
                          THEN '(NOT (pg_has_role(SESSION_USER, ''gamma_app''::name, ''MEMBER''::text) AND pg_has_role(SESSION_USER, ''gamma_outbox_worker''::name, ''MEMBER''::text)))'
                          ELSE '(tenant_id = ( SELECT outbox_worker_identity.tenant_id FROM outbox_worker_identity WHERE (outbox_worker_identity.login_name = SESSION_USER)))'
                      END
                  OR pg_get_expr(p.polqual, p.polrelid) IS DISTINCT FROM pg_get_expr(p.polwithcheck, p.polrelid)
              )
        ) THEN
            RAISE EXCEPTION 'Schema audit: worker predicate drift';
        END IF;
        IF t = 'integration_outbox' THEN
            IF NOT has_table_privilege('gamma_outbox_worker', obj.oid, 'SELECT')
               OR has_any_column_privilege('gamma_outbox_worker', obj.oid, 'INSERT,REFERENCES')
               OR has_table_privilege('gamma_outbox_worker', obj.oid, 'DELETE,TRUNCATE,TRIGGER,UPDATE')
               OR EXISTS (
                   SELECT 1 FROM pg_catalog.pg_attribute a
                   WHERE a.attrelid = obj.oid AND a.attnum > 0 AND NOT a.attisdropped
                     AND has_column_privilege('gamma_outbox_worker', obj.oid, a.attnum, 'UPDATE')
                         IS DISTINCT FROM (a.attname IN ('published_at','attempts','next_attempt_at','last_error'))
               ) THEN
                RAISE EXCEPTION 'Schema audit: unsafe outbox worker column privileges';
            END IF;
        ELSIF has_any_column_privilege('gamma_outbox_worker', obj.oid, 'SELECT,INSERT,UPDATE,REFERENCES')
           OR has_table_privilege('gamma_outbox_worker', obj.oid, 'DELETE,TRUNCATE,TRIGGER') THEN
            RAISE EXCEPTION 'Schema audit: unexpected worker access outside outbox: %', t;
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
-- Pinned expressions are PG16-specific; complete ACL review and behavioral
-- isolation still require separate evidence.

-- Replay 0009 privilege-boundary audit. This is intentionally read-only and
-- runs after Alembic upgrade in both Compose and Helm init gates.
DO $replay_audit$
DECLARE
    replay_oid oid := to_regclass('public.gateway_assertion_replay');
    executor pg_catalog.pg_roles%ROWTYPE;
    maintenance pg_catalog.pg_roles%ROWTYPE;
    cleanup_oid oid := to_regprocedure('replay_maintenance.purge_expired(integer,integer)');
BEGIN
    IF replay_oid IS NULL OR cleanup_oid IS NULL THEN
        RAISE EXCEPTION 'Replay audit: migration 0009 objects are missing';
    END IF;
    SELECT * INTO executor FROM pg_catalog.pg_roles WHERE rolname = 'gamma_replay_executor';
    SELECT * INTO maintenance FROM pg_catalog.pg_roles WHERE rolname = 'gamma_replay_maintenance';
    IF executor.oid IS NULL OR maintenance.oid IS NULL
       OR executor.rolcanlogin OR executor.rolsuper OR executor.rolbypassrls
       OR executor.rolcreatedb OR executor.rolcreaterole OR executor.rolreplication OR executor.rolinherit
       OR maintenance.rolcanlogin OR maintenance.rolsuper OR maintenance.rolbypassrls
       OR maintenance.rolcreatedb OR maintenance.rolcreaterole OR maintenance.rolreplication OR maintenance.rolinherit THEN
        RAISE EXCEPTION 'Replay audit: unsafe executor or maintenance role attributes';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members
        WHERE roleid = executor.oid OR member = executor.oid
    ) OR pg_has_role('gamma_app', executor.oid, 'MEMBER')
      OR pg_has_role('gamma_replay_maintenance', executor.oid, 'MEMBER') THEN
        RAISE EXCEPTION 'Replay audit: executor membership drift';
    END IF;
    IF has_table_privilege('gamma_app', replay_oid, 'UPDATE,DELETE,TRUNCATE,TRIGGER')
       OR has_column_privilege('gamma_app', replay_oid, 'assertion_digest', 'UPDATE')
       OR has_column_privilege('gamma_app', replay_oid, 'expires_at', 'UPDATE') THEN
        RAISE EXCEPTION 'Replay audit: application role has direct replay read/mutation privileges';
    END IF;
    IF NOT has_table_privilege(executor.rolname, replay_oid, 'SELECT,DELETE')
       OR NOT has_column_privilege(executor.rolname, replay_oid, 'expires_at', 'UPDATE')
       OR has_column_privilege(executor.rolname, replay_oid, 'assertion_digest', 'UPDATE') THEN
        RAISE EXCEPTION 'Replay audit: executor table privileges drift';
    END IF;
    IF has_any_column_privilege(maintenance.rolname, replay_oid, 'SELECT,INSERT,UPDATE,REFERENCES')
       OR has_table_privilege(maintenance.rolname, replay_oid, 'DELETE,TRUNCATE,TRIGGER') THEN
        RAISE EXCEPTION 'Replay audit: maintenance has direct table access';
    END IF;
    IF has_schema_privilege(executor.rolname, 'replay_maintenance', 'CREATE')
       OR has_schema_privilege(executor.rolname, 'public', 'CREATE')
       OR has_schema_privilege(maintenance.rolname, 'replay_maintenance', 'CREATE') THEN
        RAISE EXCEPTION 'Replay audit: unsafe schema CREATE privilege';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc p
        WHERE p.oid = cleanup_oid AND p.prosecdef
          AND p.proowner = executor.oid
          AND p.proconfig = ARRAY['search_path=pg_catalog, pg_temp']
          AND has_function_privilege(maintenance.rolname, p.oid, 'EXECUTE')
          AND NOT has_function_privilege('gamma_app', p.oid, 'EXECUTE')
          AND NOT has_function_privilege('gamma_outbox_worker', p.oid, 'EXECUTE')
          AND btrim(regexp_replace(p.prosrc, '[[:space:]]+', ' ', 'g')) =
            'DECLARE deleted integer; BEGIN IF batch_size IS NULL OR grace_seconds IS NULL OR batch_size NOT BETWEEN 1 AND 10000 OR grace_seconds NOT BETWEEN 60 AND 86400 THEN RAISE EXCEPTION ''Invalid replay cleanup policy'' USING ERRCODE = ''22023''; END IF; WITH expired AS ( SELECT assertion_digest FROM public.gateway_assertion_replay WHERE expires_at < statement_timestamp() - (grace_seconds * interval ''1 second'') ORDER BY expires_at, assertion_digest FOR UPDATE SKIP LOCKED LIMIT batch_size ) DELETE FROM public.gateway_assertion_replay AS replay USING expired WHERE replay.assertion_digest = expired.assertion_digest; GET DIAGNOSTICS deleted = ROW_COUNT; RETURN deleted; END;'
    ) THEN
        RAISE EXCEPTION 'Replay audit: SECURITY DEFINER function body, owner, search_path or grantee drift';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc p
        CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
        WHERE p.oid = cleanup_oid AND a.privilege_type = 'EXECUTE'
          AND a.grantee NOT IN (p.proowner, maintenance.oid)
    ) THEN
        RAISE EXCEPTION 'Replay audit: unexpected cleanup EXECUTE grantee';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members
        WHERE roleid = executor.oid OR member = executor.oid
    ) THEN
        RAISE EXCEPTION 'Replay audit: executor role must remain isolated';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.prosecdef
          AND has_function_privilege('gamma_app', p.oid, 'EXECUTE')
    ) THEN
        RAISE EXCEPTION 'Replay audit: application can execute public SECURITY DEFINER routine';
    END IF;
    IF (SELECT count(*) FROM pg_catalog.pg_trigger t
        JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
        WHERE t.tgrelid = replay_oid AND t.tgname = 'replay_immutable_update'
          AND t.tgtype = 18 AND t.tgenabled = 'A'
          AND p.oid = 'public.reject_replay_update()'::regprocedure
          AND NOT p.prosecdef AND p.proconfig = ARRAY['search_path=pg_catalog']) <> 1
       OR (SELECT count(*) FROM pg_catalog.pg_trigger t
        JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
        WHERE t.tgrelid = replay_oid AND t.tgname = 'replay_expiry_delete'
          AND t.tgtype = 11 AND t.tgenabled = 'A'
          AND p.oid = 'public.reject_live_replay_delete()'::regprocedure
          AND NOT p.prosecdef AND p.proconfig = ARRAY['search_path=pg_catalog']) <> 1 THEN
        RAISE EXCEPTION 'Replay audit: immutable-update or protected-delete trigger drift';
    END IF;
END
$replay_audit$;
