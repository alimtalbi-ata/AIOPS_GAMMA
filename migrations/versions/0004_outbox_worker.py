"""Proposed worker identity policy; no tenant logins provisioned."""
from alembic import op

revision = "0004_outbox_worker"
down_revision = "0003_tenant_rls"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE ROLE gamma_outbox_worker NOLOGIN NOSUPERUSER NOBYPASSRLS")
    op.execute("""
        CREATE TABLE public.outbox_worker_identity (
            login_name name PRIMARY KEY,
            tenant_id uuid NOT NULL
        )
    """)
    op.execute("REVOKE ALL ON public.outbox_worker_identity FROM PUBLIC")
    op.execute("GRANT SELECT ON public.outbox_worker_identity TO gamma_outbox_worker")
    op.execute("""
        ALTER TABLE public.outbox_worker_identity ENABLE ROW LEVEL SECURITY
    """)
    op.execute("""
        CREATE POLICY worker_self ON public.outbox_worker_identity
        FOR SELECT TO gamma_outbox_worker USING (login_name = session_user)
    """)
    op.execute("GRANT SELECT ON public.integration_outbox TO gamma_outbox_worker")
    op.execute("""
        GRANT UPDATE (published_at, attempts, next_attempt_at, last_error)
        ON public.integration_outbox TO gamma_outbox_worker
    """)
    predicate = """tenant_id = (
        SELECT tenant_id FROM public.outbox_worker_identity
        WHERE login_name = session_user
    )"""
    op.execute(f"""
        CREATE POLICY worker_identity ON public.integration_outbox
        AS RESTRICTIVE TO gamma_outbox_worker
        USING ({predicate}) WITH CHECK ({predicate})
    """)
    op.execute(f"""
        CREATE POLICY worker_access ON public.integration_outbox
        TO gamma_outbox_worker USING ({predicate}) WITH CHECK ({predicate})
    """)


def downgrade():
    op.execute("DROP POLICY worker_access ON public.integration_outbox")
    op.execute("DROP POLICY worker_identity ON public.integration_outbox")
    op.execute("REVOKE ALL ON public.integration_outbox FROM gamma_outbox_worker")
    op.execute("""
        REVOKE UPDATE (published_at, attempts, next_attempt_at, last_error)
        ON public.integration_outbox FROM gamma_outbox_worker
    """)
    op.execute("DROP TABLE public.outbox_worker_identity")
    op.execute("DROP ROLE gamma_outbox_worker")
