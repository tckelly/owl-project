"""All application SQL lives here — the only app module migration steps touch."""
import os

import psycopg
from psycopg.rows import dict_row

from app.commitment import format_commitment, parse_commitment

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/owl")

# Reads come from the parsed columns; the text column is still written (below)
# because step-1 instances read it during this step's rollout.
READ_COLUMNS = """fund_id, fund_name, manager, strategy, vintage_year,
                  commitment_cents, currency, reported_at"""


def connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def served(row):
    """Derive the commitment string from the parsed columns (API compatibility)."""
    if row is None:
        return None
    return {**row, "commitment": format_commitment(row["commitment_cents"], row["currency"])}


def list_funds():
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {READ_COLUMNS} FROM funds ORDER BY fund_id"
        ).fetchall()
    return [served(row) for row in rows]


def with_parsed_commitment(fund):
    """Dual-write (temporary, until step 3): keep the commitment text and also store
    its parsed cents and currency, so either can be the source of truth."""
    cents, currency = parse_commitment(fund["commitment"])
    return {**fund, "commitment_cents": cents, "currency": currency}


def create_fund(fund):
    """Insert a fund; returns the stored row, or None if fund_id already exists."""
    with connect() as conn:
        return served(conn.execute(
            f"""
            INSERT INTO funds (fund_id, fund_name, manager, strategy, vintage_year,
                               commitment, commitment_cents, currency, reported_at)
            VALUES (%(fund_id)s, %(fund_name)s, %(manager)s, %(strategy)s,
                    %(vintage_year)s, %(commitment)s, %(commitment_cents)s,
                    %(currency)s, %(reported_at)s)
            ON CONFLICT (fund_id) DO NOTHING
            RETURNING {READ_COLUMNS}
            """,
            with_parsed_commitment(fund),
        ).fetchone())


def update_fund(fund):
    """Replace a fund's fields; returns the stored row, or None if it doesn't exist."""
    with connect() as conn:
        return served(conn.execute(
            f"""
            UPDATE funds
            SET fund_name = %(fund_name)s, manager = %(manager)s,
                strategy = %(strategy)s, vintage_year = %(vintage_year)s,
                commitment = %(commitment)s, commitment_cents = %(commitment_cents)s,
                currency = %(currency)s, reported_at = %(reported_at)s
            WHERE fund_id = %(fund_id)s
            RETURNING {READ_COLUMNS}
            """,
            with_parsed_commitment(fund),
        ).fetchone())
