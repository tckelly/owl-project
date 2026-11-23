PY := .venv/bin/python
PORT ?= 8000
DATABASE_URL ?= postgresql://localhost:5432/owl
TEST_DATABASE_URL ?= postgresql://localhost:5432/owl_test
export DATABASE_URL

.PHONY: install seed migrate serve test

install:
	python3.14 -m venv .venv
	.venv/bin/pip install -r requirements.txt

seed:
	$(PY) scripts/seed.py

migrate:
	$(PY) -m alembic upgrade head

serve:
	$(PY) -m uvicorn app.main:app --port $(PORT)

test:
	TEST_DATABASE_URL=$(TEST_DATABASE_URL) $(PY) -m pytest
