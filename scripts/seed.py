"""Drop & recreate the database, load the CSV, then migrate to head.

Identical on every branch: the CSV is loaded at the *first* revision (where
`commitment` is raw text), then later migrations run — so the backfill path is
exercised. Like a migration, the INSERT below is a frozen snapshot of the first
revision's schema; it deliberately does not use app/db.py, which later steps change.
"""
import csv
import os
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "funds.csv"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/owl")


def recreate_database():
    dbname = conninfo_to_dict(DATABASE_URL)["dbname"]
    admin = make_conninfo(DATABASE_URL, dbname="postgres")
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(dbname)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))


def load_csv():
    with CSV_PATH.open(newline="") as f:
        rows = [
            (r["fund_id"], r["fund_name"], r["manager"], r["strategy"],
             int(r["vintage_year"]), r["commitment"], r["reported_at"])
            for r in csv.DictReader(f)
        ]
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO funds (fund_id, fund_name, manager, strategy,
                               vintage_year, commitment, reported_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    return len(rows)


def main():
    config = Config(str(ROOT / "alembic.ini"))
    first = ScriptDirectory.from_config(config).get_base()
    recreate_database()
    command.upgrade(config, first)
    count = load_csv()
    command.upgrade(config, "head")
    print(f"Seeded {count} funds")


if __name__ == "__main__":
    main()
