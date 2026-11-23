# owl-project

Take-home assessment: a minimal funds app (Postgres + Python API + React) whose real
purpose is a **zero-downtime column migration** done in stacked branches.

**Read `docs/PLAN.md` first** — it holds the brief, decisions, migration sequence and
the status checklist. Update the checklist there as work completes.

## Environment

- macOS 12 (Intel). Homebrew has no bottles for this OS — avoid brew installs that
  compile large deps (e.g. colima/qemu). No Docker.
- Postgres 16 runs natively via `brew services` (binaries in
  `/usr/local/opt/postgresql@16/bin`, data in `/usr/local/var/postgresql@16`,
  trust auth on localhost); the app connects only via `DATABASE_URL`
  (default `postgresql://localhost:5432/owl`).
- Python 3.14 (use a venv), Node 22 (nvm).

## Working contract

- **TDD from the start.** Red → green → refactor. Commit the failing test, then the
  code that makes it pass, so the history shows it. For each migration step the first
  test is: the previous step's code works against this step's schema.
- **Tests hit a real Postgres**, not mocks — schema/code mismatches are the point.
- **Simple; no speculative complexity.** Build only what the current step needs.
- **Loosely coupled — isolate dependencies at the seams that change:**
  - all SQL lives in one DB module (the only thing migration steps should touch in app code)
  - the commitment parser is a pure function with no dependencies
  - API routes stay thin; don't wrap frameworks (FastAPI, React) in our own abstractions
- **DRY**, with two deliberate exceptions: migrations are frozen snapshots (don't import
  app code that later steps change), and dual-writing old+new columns is intentional
  and temporary.

## Hard rules

- `make seed`, `make migrate`, `make serve PORT=xxxx` must work on every branch.
- Each branch: the previous branch's code must work against this branch's schema.
- SQL always names its columns — no `SELECT *`, no column-less `INSERT`.
- Never squash commits. One branch per step, each cut from the previous one.
- Ask the user before creating the GitHub repo, pushing, opening PRs or adding collaborators.
