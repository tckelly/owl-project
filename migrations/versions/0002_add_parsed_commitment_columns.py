"""Expand: add nullable commitment_cents and currency.

Nullable with no default, so this is a metadata-only change (no table rewrite)
and step-0 code, which never names these columns, keeps working.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE funds
            ADD COLUMN commitment_cents bigint,
            ADD COLUMN currency char(3)
        """
    )


def downgrade():
    op.execute("ALTER TABLE funds DROP COLUMN commitment_cents, DROP COLUMN currency")
