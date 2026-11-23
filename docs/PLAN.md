# Plan & Status

Source brief: `docs/ASSESSMENT.md`. Data: `data/funds.csv` (500 rows).

This file is the same on every branch: it is kept on `main`, which every step branch
is built on, so it stays out of the step PRs' diffs. Earlier per-step versions are in the git history.

## The brief (summary)

- **Part 1:** minimal app over the CSV — Postgres, Python API, React frontend.
  `commitment` is loaded **as text** (e.g. `$1,200,000 USD`). Commit to `main` as the starting point.
- **Part 2:** migrate `commitment` (text) → `commitment_cents bigint` + `currency char(3)`
  with zero downtime under rolling deploys.
- **The rule:** for each step, the *previous* step's code must serve correct traffic
  against the *current* step's schema. Reviewers check out two consecutive branches,
  point both at one DB, and verify the older one still works.
- **Required make targets (exactly):** `make seed` (drop & recreate the DB, load the
  CSV), `make migrate` (apply every migration up to the current checkout),
  `make serve PORT=xxxx` (run the API on that port).
- **Submission:** GitHub repo, one branch per step, each branched off the previous,
  one open PR per step (stacked: step N's PR targets step N-1's branch), reviewers
  added as collaborators. PR body: 3–4 sentences — what it does & why it's safe
  alone; what must be deployed first; anything else.
- Don't squash commits. State what's out of scope. ~2 hours total. Graded on sequencing.

## Decisions

The lightweight decision log — no separate ADRs.

**Approach & stack**
- **Keep it simple.** Light TDD: API tests for Part 1 (no frontend tests); strict
  test-first for the commitment parser; the rolling-deploy test runs step N-1's code
  against step N's schema.
- **Stack:** FastAPI + psycopg (plain SQL, explicit column lists — never `SELECT *`
  or column-less `INSERT`), Alembic for migrations, Vite + React frontend, npm (not
  pnpm: one small frontend, npm is universal for reviewers).
- **DB connection only via `DATABASE_URL`** (default `postgresql://localhost:5432/owl`).
  Postgres installed natively (Postgres.app or `brew install postgresql@16`); no Docker.
- **API has writes** (create/update fund) — without writes the migration is trivial.
- **Alembic for migrations** (standard, reviewers know it, supports Python migrations
  for the backfill). Migrations use plain SQL via `op.execute`; app code does not use
  SQLAlchemy. Rejected: a custom runner (less common, more to explain). The app never
  checks the schema revision at startup, so older code can `make serve` against a
  newer DB. Edge case: Alembic errors ("Can't locate revision") if `make migrate` runs
  from an *older* checkout against a newer DB — README says to migrate from the newest
  checkout, as a real deploy would.
- **`make seed` is identical on every branch:** drop DB → migrate to the *first*
  revision → load CSV as text → migrate to head. Works whatever order reviewers run
  targets in, and the backfill path is still exercised. `make migrate` is idempotent.
  Seed SQL is frozen in `scripts/seed.py`, outside `app/db.py`: it always loads at
  revision 0001, so its INSERT must match that schema forever, like a migration.
- **`make install` is a one-time setup step** (venv + Python deps, npm), documented in
  the README; the required targets assume it has run.

**Commitment parsing**
- **One Python parser** (pure function, `app/commitment.py`), used by app dual-writes
  *and* imported by the step-2 backfill migration. Rejected: a duplicate SQL parser
  (two parsers to keep in agreement) and a Postgres function + trigger (too complex).
  Accepted cost: the backfill migration isn't a frozen snapshot of the parser.
  The parser and its tests were committed on `main` ahead of step 1, so they are not
  in any step PR's diff.
- **Parsing rules:** bare `$` → USD (assumption); case/whitespace-insensitive;
  code may precede or follow the amount; `~` (approximate) parsed, flag dropped;
  `''`, `Not reported`, `Undisclosed`, `TBD` → NULL cents and NULL currency.
  `commitment_cents` = hundredths of the major unit for *all* currencies (incl. JPY).
  Anything else raises `ValueError`.
- **Unparseable commitments:** from step 1 the API rejects them (422), on request
  bodies only, so rows written by step-0 instances during the step-1 rollout still
  list. The step-2 backfill stores NULL cents/currency for such rows and logs their
  fund_ids rather than failing the migration (commented in the code). The seed data
  always parses (tested).
- **API response keeps `commitment` as a string** plus structured fields, so the old
  frontend keeps working. From step 2 it's derived: `format_commitment(cents, currency)`,
  e.g. `USD 1,250,000.50`; whole amounts omit `.00`; missing → `''`. It parses back to
  the same value, so old frontends and clients can re-submit it. Visible change during
  the step-2 rollout: step-1 instances show the raw text, step-2 the formatted one
  (same value) — called out in the step-2 PR.
- **Backfill race guard:** each 0003 update applies only `WHERE commitment IS NOT
  DISTINCT FROM <text read>`, so a concurrent step-1 dual-write wins. One transaction
  over 500 rows is fine here; batching for large tables is out of scope.

**Verification**
- **Rolling-deploy test** (`tests/test_rolling_deploy.py`): seeds with this checkout,
  runs `PREVIOUS_STEP`'s API from a git worktree beside this one on the same DB, and
  checks each version's writes read back through the other. `PREVIOUS_STEP` is
  updated on each branch. Compares step-0 fields only, commitments by parsed value.
  Green before a step's changes by design (a regression guard); verified to fail
  (500) against a sabotage migration renaming `commitment`.

## Implementation notes

- Python deps verified to install as prebuilt wheels on Python 3.14 / macOS 12 Intel:
  fastapi, uvicorn, psycopg[binary], alembic, pytest, httpx.
- FastAPI runs validators on `response_model` too, which made one unparseable row
  500 the whole list — hence `FundWrite` (request, validated) vs `Fund` (response).
- `alembic.ini` sets `prepend_sys_path = %(here)s` so migration 0003 can import
  `app.commitment` when run in-process by `scripts/seed.py`.
- `make test` takes ~25–45s (a fresh seed per test plus two API servers); acceptable.

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

Step notes:
- **Step 3:** no migration (`commitment` is already nullable). Requests still take a
  `commitment` string (parsed into the new columns); the text column is no longer
  written, so new rows have it NULL. Safe because step-2 instances read only the new
  columns.
- **Step 4:** migration drops `commitment` and adds the currency CHECK. To avoid a long
  lock, the CHECK is added `NOT VALID`, then `VALIDATE CONSTRAINT` runs in Alembic's
  `autocommit_block()`: the whole migration otherwise shares one transaction and the
  `ADD CONSTRAINT` lock would be held through the scan. Downgrade re-adds the column
  (nullable) — data in it is gone. The rolling test's step-0 contract still holds since
  responses keep the formatted `commitment` string.

## Working practice

- Each step: retarget `PREVIOUS_STEP` (commit) → red tests (commit) → green (commit) →
  run `make seed`/`migrate`/`serve` → check in the browser (`make web PORT=…`) →
  update this file (*Step log* row, PR description).
- A fix is committed (test-first) on the earliest affected branch. Before review, the
  step branches were rebuilt as a straight line on `main` (no squashing: every code
  commit kept, only docs-only and merge commits dropped; each branch's files
  unchanged). Once reviewers have the repo, history is not rewritten.

## Pull requests

Stacked and open: #1 `step-1-expand` → `main`, #2 step 2 → step 1, #3 step 3 → step 2,
#4 step 4 → step 3. Their descriptions are kept in `docs/PR_DESCRIPTIONS.md`.

## Out of scope (stated in README)

FX conversion, auth, pagination, deployment config, preserving the `~` flag or the
distinction between missing-value reasons, batching the backfill, restoring the text
on downgrade past step 4, frontend tests.

Questions worth revisiting after the fact are tracked in `docs/OPEN_QUESTIONS.md`.

## Status

### Step log

One row per step, added when the step is done. Detail is in each branch's commits.

| Step | Branch | Verified | Findings |
|---|---|---|---|
| setup | — | brief read, data profiled, plan agreed; Postgres 16 via brew services, `psql` works | — |
| 0 | `main` | API tests; Makefile seed/migrate/serve; React table + form; browser: list, add, edit | — |
| parser | `main` | 30 unit tests incl. all 500 CSV rows (25 missing) | 15 distinct shapes in the data |
| 1 | `step-1-expand` | 43 tests incl. rolling vs `main`; targets; curl; browser: 422 then valid add, DB dual-written | `response_model` ran the write validator on GET (fixed: `FundWrite`); browser check found raw-JSON 422 in the form (fixed, step-2 rebased) |
| 2 | `step-2-backfill-read-new` | 51 tests incl. rolling vs step 1, backfill repair; targets; browser: edit shows formatted value, DB has text + parsed | served commitment text changes format (same value); backfill race guard needed |
| 3 | `step-3-stop-writing-text` | 52 tests incl. rolling vs step 2, API with `commitment` dropped; targets; curl; browser: add + edit, DB text NULL on new row, parsed columns written | updates leave old text stale (not NULLed) — unread, dropped in step 4 |
| 4 | `step-4-drop-column` | 57 tests incl. rolling vs step 3, column dropped, CHECK rejects bad codes, downgrade; targets; constraint `convalidated`; curl; browser: list, 422 message, add, edit, DB parsed columns | VALIDATE needs its own transaction (`autocommit_block`); downgrading past 0004 leaves text empty, so the backfill test restores it from the CSV |
| README | `main` (step branches rebased onto it) | replay steps followed as written (step 3 vs step 4 worktrees, cross-writes read back); `range-diff` shows step commits unchanged; 57 tests on step 4 | README lives on `main` so GitHub shows it and every branch has it |
| review | all | tests green on every branch (36/43/51/52/57); manual replay of every consecutive pair on one DB (older seeds, newer migrates, cross-writes read back) | follow-ups recorded in `docs/OPEN_QUESTIONS.md` |
| docs | `main`, merged forward | plan, PR descriptions and open questions identical on every branch; docs absent from the step PRs' diffs; tests green on every branch | — |
| fixes | `step-1-expand` (item 1), `step-4-drop-column` (item 8), merged forward | red test committed first for each; suites 36/44/52/53/59; manual replay of every pair unchanged | lock waits were unbounded; 0004 was stuck after a failed `VALIDATE` |
| reviewer setup | `main` (Python), `step-1-expand` (fresh clone), merged forward | red test first for the clone fix; suites 36/45/53/54/60; `make test` in a fresh GitHub clone | rolling-deploy test needed every branch checked out locally; `make install` required exactly python3.14 (deps need 3.11+) |
| history | steps 1–4 rebuilt on `main` | each branch's files identical to before; `range-diff` shows every code commit unchanged; tests green on every branch | docs and merge commits outnumbered the code commits in the PRs |

### Remaining

- [x] Steps 0–4 (rolling-deploy test passing on each)
- [x] README: out of scope, the step sequence, the rolling-deploy test
- [x] Push all five branches; open stacked PRs #1–#4
- [x] Investigate `docs/OPEN_QUESTIONS.md` and record findings
- [x] Fix items 1 and 8 test-first; the rest stay proposed, deliberately not built
- [x] `make test` works in a fresh clone; `make install` takes any Python 3.11+
