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
    # API runtime uses a dedicated non-owner, non-superuser role.
    for table in TENANT_TABLES:
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO gamma_app')
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gamma_app")
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
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM gamma_app")
    for table in reversed(TENANT_TABLES):
        op.execute(f'REVOKE SELECT, INSERT, UPDATE, DELETE ON "{table}" FROM gamma_app')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
