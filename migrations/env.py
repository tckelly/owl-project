"""Alembic env: connects via DATABASE_URL. Migrations use plain SQL (op.execute)."""
import os

from alembic import context
from sqlalchemy import create_engine

url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/owl")
engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))

with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
