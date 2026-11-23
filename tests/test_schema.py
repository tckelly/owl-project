"""Migration 0004 drops the commitment text column and constrains currency."""
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parent.parent


def columns(database_url):
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'funds'
            """
        ).fetchall()
    return {name for (name,) in rows}


def set_currency(database_url, currency):
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "UPDATE funds SET currency = %s WHERE fund_id = 'F-1001'", (currency,)
        )


def test_commitment_text_column_is_dropped(seeded_db):
    assert "commitment" not in columns(seeded_db)
    assert {"commitment_cents", "currency"} <= columns(seeded_db)


@pytest.mark.parametrize("currency", ["usd", "US", "U$D"])
def test_currency_must_be_three_uppercase_letters(seeded_db, currency):
    with pytest.raises(psycopg.errors.CheckViolation):
        set_currency(seeded_db, currency)


def test_currency_may_be_null(seeded_db):
    set_currency(seeded_db, None)


def test_downgrade_re_adds_the_text_column_empty_and_drops_the_check(seeded_db):
    config = Config(str(ROOT / "alembic.ini"))
    command.downgrade(config, "0003")

    assert "commitment" in columns(seeded_db)
    with psycopg.connect(seeded_db) as conn:
        assert conn.execute(
            "SELECT count(*) FROM funds WHERE commitment IS NOT NULL"
        ).fetchone() == (0,)
    set_currency(seeded_db, "usd")
