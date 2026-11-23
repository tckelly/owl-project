import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://localhost:5432/owl_test"
)


@pytest.fixture(scope="session")
def seeded_db():
    """Seed a dedicated test database through the real `make seed` target."""
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    subprocess.run(["make", "seed"], cwd=ROOT, check=True, env=os.environ.copy())
    return TEST_DATABASE_URL


@pytest.fixture
def client(seeded_db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
