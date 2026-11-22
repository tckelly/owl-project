# Full Stack Assessment

*Adapted from the original brief. Reviewer details omitted.*

## Context

`data/funds.csv` is the data. We create our own repo.

## Part 1: Stand up the app

Build a minimal app over the CSV: **Postgres, a Python API, a React frontend.** What is
displayed on the frontend is up to us; Part 2 is the more important part.

The `commitment` column arrives as text, with values like `$1,200,000 USD`. **Load it as text.**

Commit this as the starting point.

## Part 2: Migrate the column

Move `commitment` to:

```sql
commitment_cents  bigint
currency          char(3)
```

Deploys are rolling: instances come up on the new version while others still serve the
old one, and the two overlap for several minutes. The app is never taken down for schema
changes.

**The rule:** for each step shipped, the previous step's code must serve correct traffic
against the current step's schema.

## How it is replayed

Because each branch is cut from the last, any two consecutive steps can be checked out
side by side, pointed at the same database, and the older one checked to still work.

The repo must support exactly:

- `make seed` — drop and recreate the database, load the CSV
- `make migrate` — apply every migration up to the current checkout
- `make serve PORT=xxxx` — run the API on that port

## What to submit

A link to the repo, with **one branch per step**, each branched off the previous one, and
**a PR opened for each** (left open). Reviewers are added as repo collaborators.

Each PR description needs:

- What this step does and why it's safe to deploy on its own
- What must already be deployed before it goes out
- Anything else important

Three or four sentences per PR is plenty — they will be read.

## Guidelines

- **Time:** ~2 hours total
- **AI:** encouraged
- **Don't squash commits.**
- **State what is out of scope.**

## What is evaluated

How the work is sequenced. A one-hour follow-up walks through the sequence and extends it.
