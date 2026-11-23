# PR descriptions

3–4 sentences each, per the brief: what it does and why it's safe alone; what must be
deployed first; anything else. These are the bodies of the open PRs; edit here first, then `gh pr edit`.

## step-1-expand → main

Adds nullable `commitment_cents` and `currency` columns and dual-writes them alongside
the `commitment` text; reads are unchanged. Safe alone: the columns are nullable with no
default (no table rewrite) and step-0 code never references them; requires only `main`,
with the migration run before the code rolls out. Writes with an unparseable commitment
now get a 422, and rows that step-0 instances write meanwhile are fixed by step 2's
backfill. Migrations now run with a 5s `lock_timeout` so they can't stall queries on
`funds`; the parser and its tests landed on `main` just before this step, so they aren't
in this diff.

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
code changes. Safe alone: step-3 code never names the column, the drop is metadata-only,
and the CHECK is added `NOT VALID` then validated separately, so the scan doesn't block
writes. Requires step 3 fully rolled out, since step-2 instances still write the text.
The drop is one-way (the downgrade re-adds the column empty), and 0004 is safe to re-run
if it fails partway.
