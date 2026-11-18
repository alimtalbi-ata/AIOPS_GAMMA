"""Separate replay maintenance privileges from authentication."""
from alembic import op

revision = "0008_replay_maintenance"
down_revision = "0007_replay_lock_only"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE ROLE gamma_replay_maintenance NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION")
    op.execute("REVOKE DELETE, UPDATE ON public.gateway_assertion_replay FROM gamma_app")
    op.execute("REVOKE UPDATE (expires_at) ON public.gateway_assertion_replay FROM gamma_app")
    op.execute("GRANT USAGE ON SCHEMA public TO gamma_replay_maintenance")
    op.execute("GRANT SELECT, DELETE ON public.gateway_assertion_replay TO gamma_replay_maintenance")
    op.execute("GRANT UPDATE (expires_at) ON public.gateway_assertion_replay TO gamma_replay_maintenance")
    op.execute("""
        CREATE FUNCTION public.reject_live_replay_delete() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog
        AS $body$
        BEGIN
            IF OLD.expires_at >= statement_timestamp() - interval '60 seconds' THEN
                RAISE EXCEPTION 'Replay reservation still protected' USING ERRCODE = '42501';
            END IF;
            RETURN OLD;
        END;
        $body$
    """)
    op.execute("REVOKE ALL ON FUNCTION public.reject_live_replay_delete() FROM PUBLIC")
    op.execute("""
        CREATE TRIGGER replay_expiry_delete
        BEFORE DELETE ON public.gateway_assertion_replay
        FOR EACH ROW EXECUTE FUNCTION public.reject_live_replay_delete()
    """)
    op.execute("ALTER TABLE public.gateway_assertion_replay ENABLE ALWAYS TRIGGER replay_expiry_delete")


def downgrade():
    op.execute("DROP TRIGGER replay_expiry_delete ON public.gateway_assertion_replay")
    op.execute("DROP FUNCTION public.reject_live_replay_delete()")
    op.execute("REVOKE UPDATE (expires_at) ON public.gateway_assertion_replay FROM gamma_replay_maintenance")
    op.execute("REVOKE SELECT, DELETE ON public.gateway_assertion_replay FROM gamma_replay_maintenance")
    op.execute("REVOKE USAGE ON SCHEMA public FROM gamma_replay_maintenance")
    op.execute("DROP ROLE gamma_replay_maintenance")
    op.execute("GRANT DELETE ON public.gateway_assertion_replay TO gamma_app")
    op.execute("GRANT UPDATE (expires_at) ON public.gateway_assertion_replay TO gamma_app")
