PY := .venv/bin/python
TEST_DATABASE_URL ?= postgresql://localhost:5432/owl_test

.PHONY: install test

install:
	python3.14 -m venv .venv
	.venv/bin/pip install -r requirements.txt

test:
	TEST_DATABASE_URL=$(TEST_DATABASE_URL) $(PY) -m pytest
