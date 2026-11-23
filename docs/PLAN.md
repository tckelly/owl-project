# Plan & Status

Source brief: `docs/ASSESSMENT.md`. Data: `data/funds.csv` (500 rows).

## The brief (summary)

- **Part 1:** minimal app over the CSV — Postgres, Python API, React frontend.
  `commitment` is loaded **as text** (e.g. `$1,200,000 USD`). Commit to `main` as the starting point.
- **Part 2:** migrate `commitment` (text) → `commitment_cents bigint` + `currency char(3)`
  with zero downtime under rolling deploys.
- **The rule:** for each step, the *previous* step's code must serve correct traffic
  against the *current* step's schema. Reviewers check out two consecutive branches,
  point both at one DB, and verify the older one still works.
- **Required make targets (exactly):**
  - `make seed` — drop & recreate the DB, load the CSV
  - `make migrate` — apply every migration up to the current checkout
  - `make serve PORT=xxxx` — run the API on that port
- **Submission:** GitHub repo, one branch per step, each branched off the previous,
  one open PR per step (stacked: step N's PR targets step N-1's branch). Add the
  reviewers as collaborators (usernames are in the original PDF, deliberately not
  committed — ask the user). PR body: 3–4 sentences —
  what it does & why it's safe alone; what must be deployed first; anything else.
- Don't squash commits. State what's out of scope. ~2 hours total. Graded on sequencing.

## Decisions

- **Keep it simple.** Light TDD: API tests for Part 1; strict test-first for the
  commitment parser; a replay script that runs step N-1's code against step N's schema.
- **Stack:** FastAPI + psycopg (plain SQL, explicit column lists — never `SELECT *`
  or column-less `INSERT`), Alembic for migrations, Vite + React frontend.
- **API has writes** (create/update fund) — without writes the migration is trivial.
- **API response keeps `commitment` as a string** (derived from new columns once they
  are the source of truth) plus structured fields, so the old frontend keeps working.
- **`make seed` is identical on every branch:** drop DB → migrate to the *first*
  revision → load CSV as text → migrate to head. Works whatever order reviewers run
  targets in, and the backfill path is still exercised. `make migrate` is idempotent.
- **One Python commitment parser** (pure function), used by app dual-writes *and*
  imported by the step-2 backfill migration. Rejected: a duplicate SQL parser (two
  parsers to keep in agreement) and a Postgres function + trigger (too complex).
  Accepted cost: the backfill migration isn't a frozen snapshot of the parser.

- **Alembic for migrations** (standard, reviewers know it, supports Python migrations
  for the backfill). Migrations use plain SQL via `op.execute`; app code does not use
  SQLAlchemy. The app never checks the schema revision at startup, so older code can
  `make serve` against a newer DB. Edge case: Alembic errors ("Can't locate revision")
  if `make migrate` runs from an *older* checkout against a newer DB — README says to
  migrate from the newest checkout, as a real deploy would. Rejected: a custom runner
  (less common, more to explain).
- **Python deps verified** to install as prebuilt wheels on Python 3.14 / macOS 12
  Intel: fastapi, uvicorn, psycopg[binary], alembic, pytest, httpx.

- **Unparseable commitments:** from step 1 the API rejects them (422); validation runs
  on request bodies only, so rows written by step-0 instances during the step-1 rollout
  still list. The step-2 backfill stores NULL cents/currency for such rows and logs
  their fund_ids rather than failing the migration (comment that choice in the code).
  The seed data always parses (tested).
- **Served commitment string** (from step 2): `format_commitment(cents, currency)`,
  e.g. `USD 1,250,000.50`; whole amounts omit `.00`; missing → `''`. It parses back to
  the same value, so old frontends and clients can re-submit it.
- **Rolling-deploy test** (`tests/test_rolling_deploy.py`): seeds with this checkout,
  runs `PREVIOUS_STEP`'s API from a git worktree beside this one on the same DB, and
  checks each version's writes read back through the other. Update `PREVIOUS_STEP`
  on each branch. This automates the replay checklist item.

This Decisions section is the lightweight decision log — no separate ADRs.
- **DB connection only via `DATABASE_URL`** (default `postgresql://localhost:5432/owl`).
  Postgres installed natively (Postgres.app or `brew install postgresql@16`); no Docker.
- **npm, not pnpm** — single small frontend, npm already installed and universal for reviewers.
- **Parsing rules:** bare `$` → USD (assumption); case/whitespace-insensitive;
  code may precede or follow the amount; `~` (approximate) parsed, flag dropped;
  `''`, `Not reported`, `Undisclosed`, `TBD` → NULL cents and NULL currency.
  `commitment_cents` = hundredths of the major unit for *all* currencies (incl. JPY).

## Data profile (commitment column)

| Shape | Count | Example |
|---|---|---|
| Clean | ~300 | `$15,000,000 USD` |
| Decimals (always 2dp) | 35 | `$1,250,000.75 USD` |
| GBP / EUR / JPY | 22 / 20 / 18 | `£12,500,000 GBP`, `¥1,125,000,000 JPY` |
| Code first | 16 | `USD 10,000,000` |
| No currency code | 16 | `$40,000,000` |
| No commas | 12 | `1250000 USD` |
| Lowercase code | 7 | `$3,000,000 usd` |
| Padded whitespace | 3 | `  $1,250,000 USD  ` |
| Approximate | 8 | `~$1,000,000 USD` |
| Missing | 25 | `''`, `Not reported`, `Undisclosed`, `TBD` |

Other columns are clean (unique `fund_id`, valid years/dates).

## Migration sequence

Migrations run before new code rolls out (`make migrate` then `make serve`).

| Branch | Change | Why previous step's code still works |
|---|---|---|
| `main` (step 0) | App reads/writes `commitment` text | — |
| `step-1-expand` | Add nullable `commitment_cents`, `currency`; code dual-writes (text + new) | Step-0 code ignores optional new columns |
| `step-2-backfill-read-new` | Backfill **all** rows from text (not just NULLs — step-0 writes during step-1 rollout may be stale); code reads new columns | Step-1 code already dual-writes, data agrees |
| `step-3-stop-writing-text` | Code stops reading/writing `commitment` | Step-2 code reads only new columns |
| `step-4-drop-column` | Drop `commitment`; add `CHECK (currency ~ '^[A-Z]{3}$')` | Step-3 code never references it |

4 is the minimum: merging any further pair lets old code read stale data or write
a dropped column.

## Out of scope (state in README)

FX conversion, auth, pagination, deployment config, preserving the `~` flag or the
distinction between missing-value reasons.

## Status

**Next action:** cut `step-3-stop-writing-text` from `step-2-backfill-read-new`. Set
`PREVIOUS_STEP = "step-2-backfill-read-new"` first, then stop writing `commitment`.
Inserts must still succeed while the column exists, so step 3's migration makes it
nullable if needed (it already is). Check each step in the browser before moving on.

- [x] Brief read, data profiled, plan agreed
- [x] Install Postgres natively; confirm `psql` works (Postgres 16 via brew services)
- [x] Part 1: API (tests first), seed/migrate/serve Makefile, React table + form → commit to `main`
- [x] Commitment parser (test-first) — `app/commitment.py`; unparseable input raises `ValueError`
- [x] Step 1 branch (`step-1-expand`) — PR pending GitHub repo
- [x] Step 2 branch (`step-2-backfill-read-new`) — PR pending GitHub repo
- [ ] Step 3 branch + PR
- [ ] Step 4 branch + PR
- [ ] Rolling-deploy test passing on every branch (replaces `scripts/replay.sh`)
- [ ] README (how to run, out of scope); create GitHub repo, push, open PRs, add collaborators
      (confirm with user before any GitHub action)
