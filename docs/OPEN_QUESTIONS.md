# Open questions

A self-review of the migration after it was finished: what a production version
would need, and the trade-offs worth revisiting. None of these breaks the brief's rule
(each step's previous code serves correct traffic against its schema); the
rolling-deploy test and a manual replay of every pair of steps confirm that.

Each item records what we checked, the evidence, and a proposed solution. Within the
~2-hour scope most fixes are **deliberately not built**; they are the next steps.
Items 1 and 8 were real defects in how the migrations fail, so they were fixed
test-first (a failing test committed before each fix).
File and line references are to the last step, `step-4-drop-column`.

| # | Question | Finding | Proposed |
|---|---|---|---|
| 1 | No `lock_timeout` on schema changes | **Fixed** (step 1) | `lock_timeout` on every migration, retry on timeout |
| 2 | The backfill migration imports app code | Trade-off, harmless so far | Freeze a copy of the parser in 0003 |
| 3 | Parsed columns aren't constrained together | Known gap | Two CHECK constraints in step 4 |
| 4 | Code rollback isn't covered in the PRs | Answered: one step back is safe and tested | One sentence per PR |
| 5 | Served format changes during step 2 | Answered: inherent to a correct design | No change |
| 6 | Step 3 leaves old text in place | Answered: the only correct option | No change |
| 7 | Downgrading 0004 brings the column back empty | Known gap, worse than first thought | Downgrade refills the text |
| 8 | 0004 can't be retried if it fails partway | **Fixed** (step 4) | Make 0004 safe to run twice |

The evidence below came from a scratch database seeded with `make seed`.

## 1. No `lock_timeout` on schema changes

**Finding:** known issue. **Fixed** in step 1 (PR #1), merged forward.

- **Where:** `migrations/versions/0002_add_parsed_commitment_columns.py:20`,
  `migrations/versions/0004_drop_commitment_text.py:27`.
- **Before:** `ADD COLUMN`, `DROP COLUMN` and `ADD CONSTRAINT` each need an
  `ACCESS EXCLUSIVE` lock. They are quick once they have it, but nothing limits how
  long they wait for it. While one waits, every later query on `funds` queues behind
  it, so a "metadata-only" change can stall the app.
- **Evidence:** at revision 0003, one session held a read open for 6s, then
  `make migrate` ran 0004. An ordinary `SELECT count(*) FROM funds` (normally
  instant) waited **4s**. Repeated with `PGOPTIONS='-c lock_timeout=1s'`: the read
  waited at most **1s**, the migration failed cleanly (still at 0003), and a retry
  with no blocker succeeded.
- **Fix:** `migrations/env.py:13` opens the migration connection with
  `lock_timeout=5s`, so every migration gets it, including statements in an
  autocommit block and the backfill's waits on row locks. On timeout the migration's
  transaction rolls back; retry `make migrate` (by hand or in deploy tooling). Goes
  with item 8: a timeout during 0004's `VALIDATE` caused the stuck state there.
- **Test:** `tests/test_migrations.py` rolls back the newest migration, locks `funds`
  from another connection, and expects the upgrade to fail with a lock timeout,
  leave the revision unchanged, and succeed on retry once the lock is released.
  Before the fix it was still waiting after 20s.

## 2. The backfill migration imports app code

**Finding:** trade-off, harmless so far. **Proposed:** freeze a copy of the parser
in 0003.

- **Where:** `migrations/versions/0003_backfill_parsed_commitment.py:17`
  (`from app.commitment import parse_commitment`).
- **Today:** deliberate, so there is one parser (see *Decisions* in `docs/PLAN.md`).
  Every other migration is a frozen snapshot, as the project's own rules require.
- **Evidence:** `parse_commitment` is unchanged on every branch; step 2 only added
  `format_commitment` beside it. But `make seed` runs 0003 every time, so a future
  change to the parser would silently change what this old migration does, and
  removing or renaming it would break `make seed` outright.
- **Solution:** copy `parse_commitment` into 0003, and add a test that the copy and
  the app's parser agree on all 500 CSV rows (it fails if they drift while both
  exist). Keeping the import is defensible for a short-lived migration, but freezing
  it follows the rule the other migrations follow.

## 3. The parsed columns aren't constrained together

**Finding:** known gap. **Proposed:** two CHECK constraints in step 4.

- **Where:** `migrations/versions/0004_drop_commitment_text.py:31`.
- **Today:** the only constraint is `CHECK (currency ~ '^[A-Z]{3}$')`. The parser
  always returns both values or neither, never negative, but the database doesn't
  enforce it. Once the text column is gone, the database is the only safeguard left.
- **Evidence:** on the step-4 schema, direct `UPDATE`s with cents and no currency,
  a currency and no cents, and negative cents were all accepted (a lowercase
  currency was rejected by the existing CHECK). The API then served `'None 1'` and
  `'GBP -5'` as commitments. The seeded data has **0** rows that would violate the
  proposed constraints.
- **Solution:** in step 4, add
  `CHECK ((commitment_cents IS NULL) = (currency IS NULL))` and
  `CHECK (commitment_cents >= 0)`, with the same `NOT VALID` then `VALIDATE` pattern
  as the currency check. Safe for step-3 code, which can't produce such rows.

## 4. Code rollback isn't covered in the PRs

**Finding:** answered: rolling the code back one step is safe, and already tested.
**Proposed:** one sentence per PR.

- **Where:** `docs/PR_DESCRIPTIONS.md` (all four PRs).
- **Today:** each PR explains rolling forward, not back.
- **Evidence:** rolling step N's code back to step N-1 leaves N-1's code running
  against step N's schema and data, which is exactly the mid-rollout situation the
  rolling-deploy test covers, including each version reading the other's writes.
  Rolling back **two** steps is not safe: on step-3 data, step 3 updated F-1001 to
  `$7 USD`, and step-1 code still served `USD 10,000,000` from the stale text.
  Step 4 has no code change, so rolling back its code is trivial; its schema change
  is covered by item 7.
- **Solution:** add to each PR: "Rollback: one step back is safe (the rolling-deploy
  test covers it); further back is not."

## 5. The served format changes during the step-2 rollout

**Finding:** answered: the cost of a correct design. **Proposed:** no change.

- **Where:** `served()` in `app/db.py` (from step 2).
- **Today:** step-1 instances return the raw text (`$15,000,000 USD`); step-2
  instances format it from the parsed columns (`USD 15,000,000`). Called out in the
  step-2 PR.
- **Evidence:** seen in the manual replay of step 1 against step 2: the same fund
  read `$2,000 USD` from one and `USD 2,000` from the other. The value is the same,
  and either string parses back to it, so re-submitting it works on both.
- **Why not change it:** the alternative is for step 2 to serve the text when present
  and fall back to the formatted value. That breaks during the step-3 rollout: step 3
  no longer writes the text, so step-2 instances would serve stale text for rows
  step 3 updated (the stale read shown in item 4). Clients that need a stable value
  should use `commitment_cents` and `currency`; the string is for compatibility.

## 6. Step 3 leaves old text in place on update

**Finding:** answered: the only correct option. **Proposed:** no change.

- **Where:** `update_fund()` in `app/db.py` (from step 3).
- **Today:** step-3 updates don't write `commitment`, so an updated row keeps text
  that no longer matches its parsed columns. Nothing reads it, and step 4 drops it.
- **Evidence:** NULLing the text isn't possible. Step-3 code must keep working after
  step 4 drops the column, and on that schema
  `UPDATE funds SET commitment = NULL` fails with
  `column "commitment" of relation "funds" does not exist`. No version within one
  step of step 3 reads the stale text; only a two-step rollback would (item 4).

## 7. Downgrading 0004 brings the column back empty

**Finding:** known gap, worse than first thought. **Proposed:** the downgrade refills
the text.

- **Where:** `migrations/versions/0004_drop_commitment_text.py:38`.
- **Today:** the downgrade re-adds `commitment` as an empty, nullable column. The
  README lists restoring it as out of scope.
- **Evidence:** at 0004, 475 of 500 funds have a commitment. After downgrading to
  0003, the text column holds **0** of them. Downgrading further to 0001 also drops
  the parsed columns, so **every commitment is lost**.
- **Solution:** after re-adding the column, fill it from `commitment_cents` and
  `currency` in the `USD 1,250,000.50` format, written in SQL so the migration stays
  self-contained. Every downgrade then keeps the data, and step-1/step-0 code reads
  correct values again.

## 8. 0004 can't be retried if it fails partway

**Finding:** known issue (found while testing item 1). **Fixed** in step 4 (PR #4).

- **Where:** `migrations/versions/0004_drop_commitment_text.py:27`–`35`.
- **Before:** 0004 commits the column drop and the `NOT VALID` constraint before
  `VALIDATE` runs in its own transaction. Alembic records the new revision only
  after `VALIDATE`.
- **Evidence:** with one bad currency already in the table, `make migrate` failed at
  `VALIDATE` (`CheckViolation`). Afterwards the column was gone, the constraint
  existed unvalidated, and the version still read **0003**. After fixing the bad row,
  the retry failed with `UndefinedColumn`. The database is stuck until someone fixes
  it by hand (e.g. `alembic stamp`).
- **Fix:** one `ALTER TABLE` that is safe to repeat: `DROP COLUMN IF EXISTS
  commitment`, `DROP CONSTRAINT IF EXISTS funds_currency_iso`, then
  `ADD CONSTRAINT … NOT VALID`. A retry finishes the job, and a single statement
  takes the table lock once.
- **Test:** `test_upgrade_can_be_retried_after_failing_validation` in
  `tests/test_schema.py` reproduces the failure above, fixes the row, and expects
  the retry to reach 0004 with the column gone and the constraint validated.
  Before the fix the retry failed with `UndefinedColumn`.
