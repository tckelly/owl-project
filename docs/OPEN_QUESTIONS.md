# Open questions

A self-review of the migration after it was finished: things a production version
would need to answer, or trade-offs worth revisiting. Each one records what we
noticed, where it is, and what happens today. *Findings* is filled in as we look
into each one.
File and line references are to the last step, `step-4-drop-column`.

Status: **Open** (not yet looked into), **Answered** (findings below, no change),
**Changed** (findings below, code changed).

## 1. No `lock_timeout` on schema changes

**Status:** Open

- **Where:** `migrations/versions/0002_add_parsed_commitment_columns.py:20`,
  `migrations/versions/0004_drop_commitment_text.py:21` and `:24`.
- **Today:** `ADD COLUMN`, `DROP COLUMN` and `ADD CONSTRAINT` each need an
  `ACCESS EXCLUSIVE` lock. They are quick once they have the lock, but nothing limits
  how long they wait for it.
- **Why it matters:** if a long-running transaction holds a lock on `funds`, the
  `ALTER` waits behind it, and every later read and write queues behind the `ALTER`.
  The app stalls even though the migration itself is "metadata-only".

**Findings:**

## 2. The backfill migration imports app code

**Status:** Open

- **Where:** `migrations/versions/0003_backfill_parsed_commitment.py:17`
  (`from app.commitment import parse_commitment`).
- **Today:** deliberate, so there is one parser (see *Decisions* in `docs/PLAN.md`).
  Every other migration is a frozen snapshot.
- **Why it matters:** if the parser changes later, running the migrations from
  scratch (e.g. `make seed`) backfills with the new parser, not the one that ran in
  production. An old migration's result can change without the migration changing.

**Findings:**

## 3. The parsed columns aren't constrained together

**Status:** Open

- **Where:** `migrations/versions/0004_drop_commitment_text.py:25`.
- **Today:** the only constraint is `CHECK (currency ~ '^[A-Z]{3}$')`. The parser
  always returns both values or neither, but the database doesn't enforce that.
- **Why it matters:** a row could have cents with no currency (or the reverse), or
  negative cents. Once the text column is gone, the database is the only safeguard
  left, e.g. `CHECK ((commitment_cents IS NULL) = (currency IS NULL))` and
  `CHECK (commitment_cents >= 0)`.

**Findings:**

## 4. Rolling back the code isn't covered in the PRs

**Status:** Open

- **Where:** `docs/PR_DESCRIPTIONS.md` (all four PRs).
- **Today:** each PR explains rolling forward. None says whether you can roll the
  code back to the previous step if the new version misbehaves.
- **Why it matters:** a rolling deploy is often rolled back. From reading the code,
  rolling back looks safe at every step until 0004 runs, but that isn't stated or
  tested.

**Findings:**

## 5. The served format changes during the step-2 rollout

**Status:** Open

- **Where:** `served()` in `app/db.py` (from step 2).
- **Today:** step-1 instances return the raw text (`$15,000,000 USD`); step-2
  instances format it from the parsed columns (`USD 15,000,000`). Same value, but a
  client can see the format change from one request to the next. Called out in the
  step-2 PR.
- **Why it matters:** clients that compare or display the string could notice. The
  alternative is to keep serving the text until step 3, at the cost of an extra step
  or of step 2 not really "reading the new columns".

**Findings:**

## 6. Step 3 leaves old text in place on update

**Status:** Open

- **Where:** `update_fund()` in `app/db.py` (from step 3).
- **Today:** step-3 updates stop writing `commitment`, so an updated row keeps its
  old text, which no longer matches its parsed columns. Nothing reads it, and step 4
  drops it.
- **Why it matters:** if step 3 were rolled back to step 1 (which reads the text),
  updated rows would show stale values. Setting the text to NULL would at least make
  the mismatch obvious.

**Findings:**

## 7. Downgrading 0004 brings the column back empty

**Status:** Open

- **Where:** `migrations/versions/0004_drop_commitment_text.py:32`.
- **Today:** the downgrade re-adds `commitment` as an empty, nullable column. Step-3
  code works with that; earlier steps' code would read NULL for every row.
- **Why it matters:** the downgrade could refill the column with
  `format_commitment(commitment_cents, currency)`, so that rolling back further than
  step 3 still shows correct values.

**Findings:**
