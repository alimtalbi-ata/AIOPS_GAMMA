"""Create durable, unique gateway assertion replay reservations.

Revision ID: 0002_gateway_replay
Revises: 0001_initial

This migration does not enable gateway auth or sensitive tenant reads.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_gateway_replay"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gateway_assertion_replay",
        sa.Column("assertion_digest", sa.String(length=64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_gateway_assertion_replay_expires_at",
        "gateway_assertion_replay",
        ["expires_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_gateway_assertion_replay_expires_at",
        table_name="gateway_assertion_replay",
    )
    op.drop_table("gateway_assertion_replay")
