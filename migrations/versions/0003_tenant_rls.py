"""Force transaction-local tenant isolation on tenant-owned tables.

Revision ID: 0003_tenant_rls
Revises: 0002_gateway_replay
"""
from alembic import op

revision = "0003_tenant_rls"
down_revision = "0002_gateway_replay"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "integration_inbox",
    "integration_outbox",
    "telemetry_service_bindings",
    "investigation_evidence",
)


def upgrade():
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON "{table}"
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            """
        )


def downgrade():
    for table in reversed(TENANT_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
