# Funds

A minimal funds app (Postgres, a FastAPI API and a React frontend) built to show a
zero-downtime migration of `commitment` from text (`$1,200,000 USD`) to
`commitment_cents bigint` + `currency char(3)`, under rolling deploys. Each step is a
branch cut from the previous one, with a stacked PR.

## Requirements

Postgres 16 on localhost, Python 3.11+ (developed on 3.14; pick one with
`make install PYTHON=python3.12`), Node 22. The app connects only through
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

`make seed` is the same on every branch: it loads the CSV as text at the first
migration, then migrates to head, so the backfill runs too.

## The migration

Migrations run before the new code rolls out (`make migrate`, then `make serve`).

| Branch | Schema | Code | Why the previous step's code still works |
|---|---|---|---|
| `main` (step 0) | `commitment text` | reads/writes the text | — |
| `step-1-expand` | add nullable `commitment_cents`, `currency` | dual-writes text + parsed columns; rejects unparseable input (422) | step-0 code never names the new columns |
| `step-2-backfill-read-new` | backfill every row from the text | reads the parsed columns; still dual-writes | step-1 code already dual-writes, so the data agrees |
| `step-3-stop-writing-text` | — | stops reading and writing the text | step-2 code reads only the parsed columns |
| `step-4-drop-column` | drop `commitment`; `CHECK (currency ~ '^[A-Z]{3}$')` | — | step-3 code never names the column |

Four steps is the minimum: merging any two lets old code read stale data or write a
dropped column. The API keeps returning a `commitment` string throughout (from step 2,
formatted from the parsed columns, e.g. `USD 1,250,000.50`), so older frontends and
clients keep working. Each PR says what must be deployed before it.

**Parsing rules** (`app/commitment.py`): case- and whitespace-insensitive; the
currency code may come before or after the amount; a bare `$` is assumed to be USD;
a leading `~` is accepted and dropped; `''`, `Not reported`, `Undisclosed` and `TBD`
become NULL. Cents are hundredths of the major unit for every currency, JPY included.

## Checking two consecutive steps

Run `make seed`/`make migrate` from the **newer** checkout, as a real deploy would.
`make migrate` in the older checkout is then a no-op: it reports that the database is
ahead of it and exits 0. Then serve both against the same database. For example, step 3 against step 4's schema:

```sh
git worktree add ../owl-step-3 step-3-stop-writing-text
git worktree add ../owl-step-4 step-4-drop-column
cd ../owl-step-4 && make install && make seed
make serve PORT=8004 &
cd ../owl-step-3 && make serve PORT=8003 PY=../owl-step-4/.venv/bin/python
```

Both APIs should list, create and update funds, and see each other's writes.

From step 1, `make test` automates this: `tests/test_rolling_deploy.py` seeds with
the current checkout, runs the previous step's API from a git worktree on the same
database, and checks that each version's writes read back through the other.

## Out of scope

- FX conversion between currencies
- Auth, pagination, deployment config
- Preserving the `~` (approximate) flag, or which missing-value word was used
- Batching the backfill (one transaction is fine for 500 rows; a large table would
  need batches)
- Restoring the text on downgrade past step 4: the column comes back empty
- Frontend tests (the API is tested against a real Postgres)
- Further hardening (extra constraints, a downgrade that keeps the data, a frozen
  copy of the parser in the backfill): investigated, with evidence and proposed
  fixes, in `docs/OPEN_QUESTIONS.md`. Migrations already time out on locks and
  0004 is safe to retry.

Decisions and the step log are in `docs/PLAN.md`; questions worth revisiting are in
`docs/OPEN_QUESTIONS.md`. Both are the same on every branch.
