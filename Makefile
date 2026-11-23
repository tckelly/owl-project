PY := .venv/bin/python
PYTHON ?= python3
PORT ?= 8000
DATABASE_URL ?= postgresql://localhost:5432/owl
TEST_DATABASE_URL ?= postgresql://localhost:5432/owl_test
export DATABASE_URL

.PHONY: install seed migrate serve test web

install:
	@$(PYTHON) -c 'import sys; sys.exit(sys.version_info < (3, 11) and "Python 3.11+ required; run make install PYTHON=python3.x")'
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -r requirements.txt
	cd web && npm install

seed:
	$(PY) scripts/seed.py

migrate:
	$(PY) -m alembic upgrade head

serve:
	$(PY) -m uvicorn app.main:app --port $(PORT)

test:
	TEST_DATABASE_URL=$(TEST_DATABASE_URL) $(PY) -m pytest

# Frontend dev server; proxies /funds to the API on API_PORT (default 8000).
web:
	cd web && API_PORT=$(PORT) npm run dev
