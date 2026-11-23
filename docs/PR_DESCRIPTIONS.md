# PR descriptions (drafts)

3–4 sentences each, per the brief: what it does and why it's safe alone; what must be
deployed first; anything else. Update a draft if its step changes.

## step-1-expand → main

Adds nullable `commitment_cents` and `currency` columns and makes the API write them
alongside the existing `commitment` text; reads are unchanged. Safe alone: the columns
are nullable with no default (no table rewrite), and step-0 code never references them.
Requires only `main`; run the migration before rolling out the code. New writes with an
unparseable commitment now get a 422, but rows that still-running step-0 instances write
in the meantime are tolerated, and step 2's backfill handles them.

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

_To write when step 3 is done._

## step-4-drop-column → step-3-stop-writing-text

_To write when step 4 is done._
