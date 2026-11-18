"""Permit row locking without permitting replay reservation mutation.

Revision ID: 0007_replay_lock_only
"""
from alembic import op

revision = "0007_replay_lock_only"
down_revision = "0006_worker_role_guard"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION public.reject_replay_update() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog
        AS $body$
        BEGIN
            RAISE EXCEPTION 'Replay reservations are immutable'
                USING ERRCODE = '42501';
        END;
        $body$
    """)
    op.execute("REVOKE ALL ON FUNCTION public.reject_replay_update() FROM PUBLIC")
    op.execute("""
        CREATE TRIGGER replay_immutable_update
        BEFORE UPDATE ON public.gateway_assertion_replay
        FOR EACH STATEMENT EXECUTE FUNCTION public.reject_replay_update()
    """)
    op.execute("ALTER TABLE public.gateway_assertion_replay ENABLE ALWAYS TRIGGER replay_immutable_update")
    # PostgreSQL requires UPDATE on at least one column for SELECT FOR UPDATE.
    # The statement trigger denies every UPDATE, including no-op and zero-row updates.
    op.execute("GRANT UPDATE (expires_at) ON public.gateway_assertion_replay TO gamma_app")


def downgrade():
    op.execute("REVOKE UPDATE (expires_at) ON public.gateway_assertion_replay FROM gamma_app")
    op.execute("DROP TRIGGER replay_immutable_update ON public.gateway_assertion_replay")
    op.execute("DROP FUNCTION public.reject_replay_update()")
