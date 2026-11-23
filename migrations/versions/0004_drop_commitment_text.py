"""Contract: drop the commitment text column; require currency to be an ISO-style code.

Safe once step 3 is fully rolled out: step-3 code never names `commitment`.
DROP COLUMN is metadata-only (no table rewrite).

The CHECK is added NOT VALID (brief lock, no scan), committed, then validated in a
separate transaction, which scans the table without blocking reads or writes.

Because the first part commits before VALIDATE, a failed VALIDATE (bad data, or a
lock timeout) leaves this half-applied with the revision still at 0003. Every
statement is safe to repeat, so retrying the migration finishes it.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE funds
            DROP COLUMN IF EXISTS commitment,
            DROP CONSTRAINT IF EXISTS funds_currency_iso,
            ADD CONSTRAINT funds_currency_iso
                CHECK (currency ~ '^[A-Z]{3}$') NOT VALID
        """
    )
    with op.get_context().autocommit_block():
        op.execute("ALTER TABLE funds VALIDATE CONSTRAINT funds_currency_iso")


def downgrade():
    # The text is gone: the column comes back nullable and empty. Step-3 code
    # (which never reads it) works; earlier steps' code would not.
    op.execute("ALTER TABLE funds DROP CONSTRAINT funds_currency_iso")
    op.execute("ALTER TABLE funds ADD COLUMN commitment text")
