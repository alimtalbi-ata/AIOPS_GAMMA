"""Deny Outbox worker policy access for overlapping API identities."""
from alembic import op

revision = "0006_worker_role_guard"
down_revision = "0005_worker_policy_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE POLICY worker_role_separation ON public.integration_outbox
        AS RESTRICTIVE TO PUBLIC
        USING (NOT (pg_has_role(session_user, 'gamma_app', 'MEMBER')
                    AND pg_has_role(session_user, 'gamma_outbox_worker', 'MEMBER')))
        WITH CHECK (NOT (pg_has_role(session_user, 'gamma_app', 'MEMBER')
                    AND pg_has_role(session_user, 'gamma_outbox_worker', 'MEMBER')))
    """)


def downgrade():
    op.execute("DROP POLICY worker_role_separation ON public.integration_outbox")
