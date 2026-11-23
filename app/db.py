"""All application SQL lives here — the only app module migration steps touch."""
import os

import psycopg
from psycopg.rows import dict_row

from app.commitment import parse_commitment

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/owl")

COLUMNS = """fund_id, fund_name, manager, strategy, vintage_year,
             commitment, reported_at"""


def connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def list_funds():
    with connect() as conn:
        return conn.execute(
            f"SELECT {COLUMNS} FROM funds ORDER BY fund_id"
        ).fetchall()


def with_parsed_commitment(fund):
    """Dual-write (temporary, until step 3): keep the commitment text and also store
    its parsed cents and currency, so either can be the source of truth."""
    cents, currency = parse_commitment(fund["commitment"])
    return {**fund, "commitment_cents": cents, "currency": currency}


def create_fund(fund):
    """Insert a fund; returns the stored row, or None if fund_id already exists."""
    with connect() as conn:
        return conn.execute(
            f"""
            INSERT INTO funds ({COLUMNS}, commitment_cents, currency)
            VALUES (%(fund_id)s, %(fund_name)s, %(manager)s, %(strategy)s,
                    %(vintage_year)s, %(commitment)s, %(reported_at)s,
                    %(commitment_cents)s, %(currency)s)
            ON CONFLICT (fund_id) DO NOTHING
            RETURNING {COLUMNS}
            """,
            with_parsed_commitment(fund),
        ).fetchone()


def update_fund(fund):
    """Replace a fund's fields; returns the stored row, or None if it doesn't exist."""
    with connect() as conn:
        return conn.execute(
            f"""
            UPDATE funds
            SET fund_name = %(fund_name)s, manager = %(manager)s,
                strategy = %(strategy)s, vintage_year = %(vintage_year)s,
                commitment = %(commitment)s, reported_at = %(reported_at)s,
                commitment_cents = %(commitment_cents)s, currency = %(currency)s
            WHERE fund_id = %(fund_id)s
            RETURNING {COLUMNS}
            """,
            with_parsed_commitment(fund),
        ).fetchone()
