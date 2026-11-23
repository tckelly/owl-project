"""`make migrate`: apply every migration up to this checkout's head.

If the database is at a revision this checkout doesn't have, a newer step has
already migrated it (as in a rolling deploy): there is nothing to apply, so say
so and exit 0 instead of failing with Alembic's "Can't locate revision".
"""
import os
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parent.parent
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/owl")


def current_revision():
    with psycopg.connect(DATABASE_URL) as conn:
        if conn.execute("SELECT to_regclass('alembic_version')").fetchone()[0] is None:
            return None
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None


def main():
    config = Config(str(ROOT / "alembic.ini"))
    known = {script.revision for script in ScriptDirectory.from_config(config).walk_revisions()}
    current = current_revision()
    if current is not None and current not in known:
        print(f"Database is at revision {current}, ahead of this checkout; nothing to apply.")
        return
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
