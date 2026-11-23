"""Alembic env: connects via DATABASE_URL. Migrations use plain SQL (op.execute)."""
import os

from alembic import context
from sqlalchemy import create_engine

url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/owl")

# A migration waiting for a lock makes every later query on the table queue
# behind it. Give up after 5s instead (the transaction rolls back) and retry.
engine = create_engine(
    url.replace("postgresql://", "postgresql+psycopg://", 1),
    connect_args={"options": "-c lock_timeout=5s"},
)

with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
