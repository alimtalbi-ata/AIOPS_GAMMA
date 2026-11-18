"""Separate API tenant policy from worker identity policy."""
from alembic import op

revision = "0005_worker_policy_scope"
down_revision = "0004_outbox_worker"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER POLICY tenant_isolation ON public.integration_outbox TO gamma_app")


def downgrade():
    op.execute("ALTER POLICY tenant_isolation ON public.integration_outbox TO PUBLIC")
