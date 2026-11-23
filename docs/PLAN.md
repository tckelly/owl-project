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
- **Required make targets (exactly):** `make seed` (drop & recreate the DB, load the
  CSV), `make migrate` (apply every migration up to the current checkout),
  `make serve PORT=xxxx` (run the API on that port).
- **Submission:** GitHub repo, one branch per step, each branched off the previous,
  one open PR per step (stacked: step N's PR targets step N-1's branch). Add the
  reviewers as collaborators (usernames are in the original PDF, deliberately not
  committed — ask the user). PR body: 3–4 sentences —
  what it does & why it's safe alone; what must be deployed first; anything else.
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

**Commitment parsing**
- **One Python parser** (pure function, `app/commitment.py`), used by app dual-writes
  *and* imported by the step-2 backfill migration. Rejected: a duplicate SQL parser
  (two parsers to keep in agreement) and a Postgres function + trigger (too complex).
  Accepted cost: the backfill migration isn't a frozen snapshot of the parser.
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
- **Rolling-deploy test** (`tests/test_rolling_deploy.py`, replaces the planned
  `scripts/replay.sh`): seeds with this checkout, runs `PREVIOUS_STEP`'s API from a git
  worktree beside this one on the same DB, and checks each version's writes read back
  through the other. Update `PREVIOUS_STEP` on each branch. Compares step-0 fields only,
  commitments by parsed value. Green before a step's changes by design (a regression
  guard); verified to fail (500) against a sabotage migration renaming `commitment`.

## Implementation notes

- Python deps verified to install as prebuilt wheels on Python 3.14 / macOS 12 Intel:
  fastapi, uvicorn, psycopg[binary], alembic, pytest, httpx.
- FastAPI runs validators on `response_model` too, which made one unparseable row
  500 the whole list — hence `FundWrite` (request, validated) vs `Fund` (response).
- `alembic.ini` sets `prepend_sys_path = %(here)s` so migration 0003 can import
  `app.commitment` when run in-process by `scripts/seed.py`.
- `make test` takes ~25s (a fresh seed per test plus two API servers); acceptable.
- Playwright writes `.playwright-mcp/` (gitignored); delete it after a session.

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

Notes for the remaining steps:
- **Step 3:** no migration (`commitment` is already nullable). Requests still take a
  `commitment` string (parsed into the new columns); the text column is no longer
  written, so new rows have it NULL. Safe because step-2 instances read only the new
  columns. Remove the dual-write helper's text half and the "still written" comment.
- **Step 4:** migration drops `commitment` and adds the currency CHECK. To avoid a long
  lock, add it `NOT VALID` then `VALIDATE CONSTRAINT`. Downgrade re-adds the column
  (nullable) — data in it is gone. The rolling test's step-0 contract still holds since
  responses keep the formatted `commitment` string.

## Working practice

- Each step: retarget `PREVIOUS_STEP` (commit) → red tests (commit) → green (commit) →
  run `make seed`/`migrate`/`serve` → **check in the browser** (`make web PORT=…`,
  Playwright) → update this file (*Step log* row, Next action, PR draft).
- Branches are unpushed, so fixing an earlier step and rebasing later ones onto it is
  fine (no squashing). Once pushed, never rewrite history; fix forward on each branch.

## Submission (GitHub)

- Repo `tckelly/owl-project` exists: **private, empty**, set as `origin`; `gh` is
  logged in as `tckelly`.
- Agreed: finish steps 3–4 and the README, **then** push all five branches at once and
  open four stacked PRs (step 1 → `main`, step N → step N-1), left open.
- **Still needed from the user before pushing:** confirm visibility (private + reviewer
  collaborators, as the brief implies, or public) and the reviewers' GitHub usernames.
  Ask again before every GitHub action.
- PR bodies: drafts in `docs/PR_DESCRIPTIONS.md`.

## Out of scope (state in README)

FX conversion, auth, pagination, deployment config, preserving the `~` flag or the
distinction between missing-value reasons.

## Status

**Next action:** step 4 — cut `step-4-drop-column` from `step-3-stop-writing-text`
and follow *Working practice* (see notes under *Migration sequence*). Then README and
the submission steps above.

### Step log

One row per step, added when the step is done. Detail is in each branch's commits.
PRs for all steps are pending the push (see *Submission*).

| Step | Branch | Verified | Findings |
|---|---|---|---|
| setup | — | brief read, data profiled, plan agreed; Postgres 16 via brew services, `psql` works | — |
| 0 | `main` | API tests; Makefile seed/migrate/serve; React table + form; browser: list, add, edit | — |
| parser | `main` | 30 unit tests incl. all 500 CSV rows (25 missing) | 15 distinct shapes in the data |
| 1 | `step-1-expand` | 43 tests incl. rolling vs `main`; targets; curl; browser: 422 then valid add, DB dual-written | `response_model` ran the write validator on GET (fixed: `FundWrite`); browser check found raw-JSON 422 in the form (fixed, step-2 rebased) |
| 2 | `step-2-backfill-read-new` | 51 tests incl. rolling vs step 1, backfill repair; targets; browser: edit shows formatted value, DB has text + parsed | served commitment text changes format (same value); backfill race guard needed |
| 3 | `step-3-stop-writing-text` | 52 tests incl. rolling vs step 2, API with `commitment` dropped; targets; curl; browser: add + edit, DB text NULL on new row, parsed columns written | updates leave old text stale (not NULLed) — unread, dropped in step 4 |
| 4 | `step-4-drop-column` | | |

### Remaining

- [x] Step 3 (rolling-deploy test passing)
- [ ] Step 4 (rolling-deploy test passing)
- [ ] README: add out of scope, the step sequence, and the rolling-deploy test
- [ ] Push, open stacked PRs, add collaborators (confirm with user first; see *Submission*)
