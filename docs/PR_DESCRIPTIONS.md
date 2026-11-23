# PR descriptions

3–4 sentences each, per the brief: what it does and why it's safe alone; what must be
deployed first; anything else. These are the bodies of the open PRs; edit here first, then `gh pr edit`.

## step-1-expand → main

Adds nullable `commitment_cents` and `currency` columns and makes the API write them
alongside the existing `commitment` text; reads are unchanged. Safe alone: the columns
are nullable with no default (no table rewrite), and step-0 code never references them.
Requires only `main`; run the migration before rolling out the code. New writes with an
unparseable commitment now get a 422, but rows that still-running step-0 instances write
in the meantime are tolerated, and step 2's backfill handles them. The parser
this step uses (`app/commitment.py`) and its tests were committed on `main` just before
this step (e6467ed, 73e93ad), so they aren't in this diff. Migrations now run with a 5s
`lock_timeout`, so one stuck behind a long transaction fails and is retried instead of
stalling every query on `funds`.

## step-2-backfill-read-new → step-1-expand

Backfills `commitment_cents`/`currency` from the text for every row and switches reads
to them; the API still returns a `commitment` string (now formatted from the new
columns) and keeps dual-writing the text. Safe alone: step-1 instances already
dual-write, so both versions agree, and each backfill update only applies if the text
hasn't changed since it was read. Requires step 1 fully rolled out, so no step-0
instance writes text-only rows after the backfill. Unparseable legacy text (only step-0
could write it) is stored as NULL and logged, and the commitment string's format
changes (e.g. `$15,000,000 USD` becomes `USD 15,000,000`; same value).

## step-3-stop-writing-text → step-2-backfill-read-new

Stops the API from writing the `commitment` text column: requests still take a
`commitment` string, but only its parsed `commitment_cents`/`currency` are stored, and
nothing reads or writes the text any more. No migration. Safe alone: step-2
instances already read only the parsed columns, so text left NULL (new rows) or stale
(updated rows) is never served. Requires step 2 fully rolled out, since step-1
instances still read the text. A test runs this code with the column dropped, which
prepares step 4.

## step-4-drop-column → step-3-stop-writing-text

Drops the `commitment` text column and adds `CHECK (currency ~ '^[A-Z]{3}$')`; no app
changes, since the API already derives the `commitment` string from the parsed columns.
Safe alone: step-3 code never names the column, and the drop is metadata-only. The
CHECK is added `NOT VALID` and validated in its own transaction, so the scan doesn't
block writes. Requires step 3 fully rolled out, since step-2 instances still write the
text. The drop can't be undone: the downgrade re-adds the column empty, which only
step-3 code tolerates. If 0004 fails after its first part
commits (e.g. at `VALIDATE`), re-running it finishes the job.
