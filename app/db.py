"""All application SQL lives here — the only app module migration steps touch."""
import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/owl")


def connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def list_funds():
    with connect() as conn:
        return conn.execute(
            """
            SELECT fund_id, fund_name, manager, strategy, vintage_year,
                   commitment, reported_at
            FROM funds
            ORDER BY fund_id
            """
        ).fetchall()
