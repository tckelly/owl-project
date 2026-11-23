"""`make migrate` in an older checkout, against a database a newer step migrated.

In a rolling deploy (and in the reviewers' replay) the newer step migrates the
shared database; the older checkout has nothing to apply and must not fail.
"""
import os
import subprocess
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent


def make_migrate(database_url):
    return subprocess.run(
        ["make", "migrate"], cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "DATABASE_URL": database_url},
    )


def revision(database_url):
    with psycopg.connect(database_url) as conn:
        return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def test_migrate_succeeds_when_the_database_is_ahead_of_this_checkout(seeded_db):
    with psycopg.connect(seeded_db) as conn:
        conn.execute("UPDATE alembic_version SET version_num = '9999'")

    result = make_migrate(seeded_db)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ahead of this checkout" in result.stdout
    assert revision(seeded_db) == "9999"


def test_migrate_at_head_is_a_no_op(seeded_db):
    before = revision(seeded_db)

    result = make_migrate(seeded_db)

    assert result.returncode == 0, result.stdout + result.stderr
    assert revision(seeded_db) == before
