"""Backfill commitment_cents and currency from the commitment text, for every row.

Every row, not just NULLs: step-0 instances still running during the step-1
rollout wrote text only, leaving the parsed columns NULL or stale.

Imports the app's parser (one parser, see docs/PLAN.md), so unlike other
migrations this one is not a frozen snapshot.

Revision ID: 0003
Revises: 0002
"""
import logging

from alembic import op
from sqlalchemy import text

from app.commitment import parse_commitment

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

log = logging.getLogger(__name__)


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(text("SELECT fund_id, commitment FROM funds")).fetchall()
    updates = []
    for fund_id, commitment in rows:
        try:
            cents, currency = parse_commitment(commitment)
        except ValueError:
            # Store NULL rather than fail: one bad row (only step-0 code could write
            # it) shouldn't block the deploy. Logged so it can be fixed by hand.
            log.warning("Unparseable commitment for %s: %r; stored NULL", fund_id, commitment)
            cents, currency = None, None
        updates.append(
            {"fund_id": fund_id, "commitment": commitment, "cents": cents, "currency": currency}
        )
    # Only if the text is unchanged since we read it: a step-1 instance that wrote
    # this row meanwhile has already dual-written the correct values.
    conn.execute(
        text(
            """
            UPDATE funds SET commitment_cents = :cents, currency = :currency
            WHERE fund_id = :fund_id AND commitment IS NOT DISTINCT FROM :commitment
            """
        ),
        updates,
    )


def downgrade():
    pass  # Data-only; step-1 code works with the parsed columns filled.
