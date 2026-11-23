"""Migrations must not stall the app behind a lock they can't get.

While a migration waits for a lock on `funds`, every later query on the table
queues behind it. So a migration gives up quickly instead, leaving the database
unchanged, and the deploy retries it.
"""
import os
import subprocess
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent


def alembic(*args):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True, timeout=20,
    )


def revision(database_url):
    with psycopg.connect(database_url) as conn:
        return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def test_migration_gives_up_on_a_lock_it_cannot_get(seeded_db):
    assert alembic("downgrade", "-1").returncode == 0
    before = revision(seeded_db)

    with psycopg.connect(seeded_db) as blocker:
        # Held until the block ends: a stand-in for any long transaction.
        blocker.execute("LOCK TABLE funds IN ACCESS EXCLUSIVE MODE")
        result = alembic("upgrade", "head")

    assert result.returncode != 0
    assert "lock timeout" in result.stderr
    assert revision(seeded_db) == before
    assert alembic("upgrade", "head").returncode == 0
