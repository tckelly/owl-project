"""Migration 0003 backfills commitment_cents/currency from the text for every row."""
import csv
import logging
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config

from app.commitment import parse_commitment

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "funds.csv"


def stored(database_url):
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "SELECT fund_id, commitment_cents, currency FROM funds"
        ).fetchall()
    return {fund_id: (cents, currency) for fund_id, cents, currency in rows}


def test_seed_backfills_every_row_from_the_csv_text(seeded_db):
    with CSV_PATH.open(newline="") as f:
        expected = {r["fund_id"]: parse_commitment(r["commitment"]) for r in csv.DictReader(f)}

    assert stored(seeded_db) == expected


def test_backfill_repairs_rows_written_by_step0_code_during_step1_rollout(seeded_db, caplog):
    config = Config(str(ROOT / "alembic.ini"))
    command.downgrade(config, "0002")
    with psycopg.connect(seeded_db) as conn:
        # Step-0 code writes only the text, leaving parsed columns NULL or stale.
        conn.execute("UPDATE funds SET commitment_cents = NULL, currency = NULL WHERE fund_id = 'F-1001'")
        conn.execute("UPDATE funds SET commitment = '£5,000 GBP' WHERE fund_id = 'F-1002'")
        conn.execute("UPDATE funds SET commitment = 'about 5m' WHERE fund_id = 'F-1003'")

    with caplog.at_level(logging.WARNING):
        command.upgrade(config, "head")

    rows = stored(seeded_db)
    assert rows["F-1001"] == (1_000_000_000, "USD")
    assert rows["F-1002"] == (500_000, "GBP")
    assert rows["F-1003"] == (None, None)
    assert "F-1003" in caplog.text
