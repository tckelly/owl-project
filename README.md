# Funds

A minimal funds app — Postgres, a FastAPI API and a React frontend — used to show a
zero-downtime migration of `commitment` (text) to `commitment_cents bigint` +
`currency char(3)`. See `docs/PLAN.md` for the migration sequence and decisions.

## Requirements

Postgres 16 on localhost, Python 3.14, Node 22. The app connects only through
`DATABASE_URL` (default `postgresql://localhost:5432/owl`).

## Run

```sh
make install          # venv + Python deps, npm install
make seed             # drop & recreate the DB, load data/funds.csv
make migrate          # apply every migration up to this checkout
make serve PORT=8000  # API on :8000  (GET/POST /funds, PUT /funds/{id})
make web PORT=8000    # frontend on :5173, proxying to the API on PORT
make test             # tests against a real Postgres (owl_test)
```

Run `make migrate` from the newest checkout when comparing two branches: an older
checkout's Alembic doesn't know newer revisions.
