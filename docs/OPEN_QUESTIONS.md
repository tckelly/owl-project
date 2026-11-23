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
| 9 | 0004 drops text that 0003 couldn't parse | Known gap, can't occur with this data | 0004 refuses to run while such rows exist |
| 10 | The backfill doesn't scale to a large table | Known gap, fine for 500 rows | Batched backfill outside the migration |
| 11 | Step 1 starts rejecting unparseable commitments | Answered: needed to dual-write | No change |
| 12 | Step 2 both backfills and switches reads | Answered: safe while the backfill is a migration | Split it if the backfill moves out (item 10) |
| 13 | `make migrate` exits 0 when the database is ahead | Answered: only for a revision it doesn't know, and it says so | No change |

The evidence below came from a scratch database seeded with `make seed`.

## 1. No `lock_timeout` on schema changes

**Finding:** known issue. **Fixed** in step 1 (PR #1).

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
  `'GBP -5'` as commitments. Worse, −501 cents was served as `'GBP -6.99'` (a wrong
  value, not just a negative one), and a currency with no cents as `''` (the
  currency silently dropped). The seeded data has **0** rows that would violate the
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

## 9. 0004 drops text that 0003 couldn't parse

**Finding:** known gap; deliberately not built.

- **Where:** `migrations/versions/0003_backfill_parsed_commitment.py` stores NULL
  (and logs a warning) for text it can't parse; `0004` then drops the column.
- **Risk:** that text would be lost. It can only exist if step-0 instances wrote
  unparseable text during the step-1 rollout; the CSV has none (all 500 rows parse),
  and from step 1 the API rejects it (422).
- **Proposed:** before dropping, 0004 refuses to run if any row has NULL parsed
  columns and text that doesn't parse. Not "any NULL parsed columns": step 3 leaves
  old text in place when a write sets a missing value, so that would block safe deploys.
- **Why not built:** about 75 lines of migration and tests (and a second migration
  importing the app's parser) for a case this data can't produce. The operator
  already gets 0003's warning to fix those rows before step 4.

## 10. The backfill doesn't scale to a large table

**Finding:** known gap; fine for 500 rows. **Proposed:** a batched backfill outside
the migration.

- **Where:** `migrations/versions/0003_backfill_parsed_commitment.py:27`–`52`.
- **Today:** 0003 reads every row into memory, then updates them all in the
  migration's single transaction. Each updated row stays locked until that
  transaction commits, so an app write to a row the backfill has already touched
  waits for the whole backfill. The 5s `lock_timeout` (item 1) bounds the
  migration's waits, not the app's.
- **Evidence:** on the seeded database, 0003 runs in about a second, including Python
  start-up. Batching the backfill is listed as out of scope in the README.
- **Solution:** at, say, 100M rows, run the backfill as a separate job after 0002,
  not as a migration: walk `fund_id` in batches of a few thousand, each batch in its
  own short transaction, keeping the "only if the text is unchanged" check per row.
  This is safe to run while step 1 serves traffic, because step 1 already
  dual-writes: any row changed during the job is already correct. The job can stop
  and resume from the last `fund_id`, and a final check confirms no row still
  has text that parses but NULL parsed columns. The 500-row brief didn't need it.

## 11. Step 1 starts rejecting unparseable commitments

**Finding:** answered: needed to dual-write. **Proposed:** no change.

- **Where:** `FundWrite` in `app/main.py` (from step 1).
- **Today:** step 0 stores any text; from step 1, a write whose commitment doesn't
  parse gets a 422. That tightens the API in the middle of a migration.
- **Evidence:** `tests/test_funds_api.py` (step 1): `about 5m` is rejected on create,
  and `£1 USD` (symbol and code disagree) on update, leaving the stored row
  unchanged. Rows that don't parse still list, because only request bodies are
  validated (`Fund` vs `FundWrite`).
- **Why not change it:** step 1 must store cents and currency next to the text, and
  there is nothing correct to store for text that doesn't parse. Accepting it would
  mean writing NULLs that look like "no commitment", and step 4 would then drop the
  only copy (the risk in item 9). Every value in the data parses, so no real client
  sending the same shapes is affected; the 422 names the field and the reason.

## 12. Step 2 both backfills and switches reads

**Finding:** answered: safe while the backfill is a migration. **Proposed:** split it
if the backfill moves out of the migration (item 10).

- **Where:** `migrations/versions/0003_backfill_parsed_commitment.py` and `app/db.py`
  in step 2.
- **Today:** one step runs the backfill and ships code that reads the parsed columns.
- **Why it's safe:** migrations run before the new code rolls out, and 0003 commits
  every row before any step-2 instance starts. While it runs, only step-1 instances
  serve, and they read the text. A separate "backfill only" step would be a deploy
  with no code change, and add no safety.
- **When to split:** once the backfill is a long-running job (item 10), the code that
  reads the new columns must not ship until the job has finished and been checked.
  That becomes its own step: step 2 runs the backfill, step 3 switches reads, and the
  sequence grows to five.

## 13. `make migrate` exits 0 when the database is ahead

**Finding:** answered: it only skips a revision this checkout doesn't know, and says
so. **Proposed:** no change.

- **Where:** `scripts/migrate.py` (on `main`, so every branch has it).
- **Today:** if the database's revision isn't one of this checkout's migrations,
  `make migrate` prints `Database is at revision …, ahead of this checkout; nothing to
  apply.` and exits 0, instead of failing with Alembic's "Can't locate revision".
  That is what lets the older checkout in a replay run `make migrate && make serve`.
- **Risk:** pointed at the wrong database (one at an unrelated revision), it would
  also exit 0 rather than fail.
- **Evidence:** `tests/test_make_migrate.py` sets the revision to `9999`: exit 0, the
  message printed, the revision untouched. A database at a known revision (or empty)
  is migrated to head as before. The app never checks the revision at startup, so
  the skip doesn't hide anything the app depends on.
- **Why not change it:** a stricter check (exit 0 only if the unknown revision is a
  newer step of this project) needs the newer migrations, which an older checkout
  doesn't have. A deploy only runs `make migrate` from the newest checkout, where the
  skip can't happen.
