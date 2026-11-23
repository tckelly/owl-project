"""Create funds table with commitment as raw text.

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE funds (
            fund_id      text PRIMARY KEY,
            fund_name    text NOT NULL,
            manager      text NOT NULL,
            strategy     text NOT NULL,
            vintage_year integer NOT NULL,
            commitment   text,
            reported_at  date NOT NULL
        )
        """
    )


def downgrade():
    op.execute("DROP TABLE funds")
