"""Bound replay cleanup at the PostgreSQL privilege boundary."""
from alembic import op

revision = "0009_replay_bounded"
down_revision = "0008_replay_maintenance"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE ROLE gamma_replay_executor NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION")
    op.execute("CREATE SCHEMA replay_maintenance")
    op.execute("REVOKE ALL ON SCHEMA replay_maintenance FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public TO gamma_replay_executor")
    op.execute("GRANT USAGE ON SCHEMA replay_maintenance TO gamma_replay_executor, gamma_replay_maintenance")
    op.execute("GRANT SELECT, DELETE ON public.gateway_assertion_replay TO gamma_replay_executor")
    op.execute("GRANT UPDATE (expires_at) ON public.gateway_assertion_replay TO gamma_replay_executor")
    op.execute("""
        CREATE FUNCTION replay_maintenance.purge_expired(batch_size integer, grace_seconds integer)
        RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $body$
        DECLARE deleted integer;
        BEGIN
            IF batch_size IS NULL OR grace_seconds IS NULL OR
               batch_size NOT BETWEEN 1 AND 10000 OR grace_seconds NOT BETWEEN 60 AND 86400 THEN
                RAISE EXCEPTION 'Invalid replay cleanup policy' USING ERRCODE = '22023';
            END IF;
            WITH expired AS (
                SELECT assertion_digest FROM public.gateway_assertion_replay
                WHERE expires_at < statement_timestamp() - (grace_seconds * interval '1 second')
                ORDER BY expires_at, assertion_digest
                FOR UPDATE SKIP LOCKED LIMIT batch_size
            )
            DELETE FROM public.gateway_assertion_replay AS replay
            USING expired WHERE replay.assertion_digest = expired.assertion_digest;
            GET DIAGNOSTICS deleted = ROW_COUNT;
            RETURN deleted;
        END;
        $body$
    """)
    op.execute("REVOKE ALL ON FUNCTION replay_maintenance.purge_expired(integer,integer) FROM PUBLIC")
    op.execute("GRANT CREATE ON SCHEMA replay_maintenance TO gamma_replay_executor")
    op.execute("ALTER FUNCTION replay_maintenance.purge_expired(integer,integer) OWNER TO gamma_replay_executor")
    op.execute("REVOKE CREATE ON SCHEMA replay_maintenance FROM gamma_replay_executor")
    op.execute("GRANT EXECUTE ON FUNCTION replay_maintenance.purge_expired(integer,integer) TO gamma_replay_maintenance")
    op.execute("REVOKE SELECT, DELETE ON public.gateway_assertion_replay FROM gamma_replay_maintenance")
    op.execute("REVOKE UPDATE (expires_at) ON public.gateway_assertion_replay FROM gamma_replay_maintenance")


def downgrade():
    raise RuntimeError("Replay security downgrade refused; use reviewed forward recovery")
