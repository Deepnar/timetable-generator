# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A standalone timetable-generation backend (FastAPI + SQLAlchemy 2.0 + PostgreSQL) for
institutions. It manages schedulable resources, runs a constraint-driven solver to produce
candidate timetables, and lets an admin select and publish one. It is the product itself, not a
microservice for another ERP. Current checkpoint: greedy and OR-Tools (CP-SAT) solvers working,
data-driven constraint registry, soft-constraint scoring; async generation and a frontend are
planned (see `documentation/`).

## Environment & commands

Dependencies are managed exclusively with **uv** — never `pip`/`requirements.txt`. Either activate
the venv (`source .venv/bin/activate`) or prefix commands with `uv run`.

```bash
uv sync                                              # install deps into managed .venv
cd docker && docker compose up -d                    # start PostgreSQL 15 (see ports note below)
uv run alembic upgrade head                          # apply migrations
uv run uvicorn app.main:app --reload --port 8000     # dev server → http://localhost:8000/docs
uv run alembic revision --autogenerate -m "message"  # new migration after model changes
uv add <package>                                     # add a dependency
```

**Postgres runs on host port `5433`**, not the default 5432 (`docker/docker-compose.yml` maps
`5433:5432`; `.env` must set `DB_PORT=5433`). Note `app/config.py` still defaults `DB_PORT` to
`5432` — the `.env` value is what matters at runtime.

## Tests

There are two independent test entry points; they are **not** pytest and pytest is not installed.

- **`uv run python -m app.tests`** — the real integration suite. `app/tests/conftest.py` stands up a
  FastAPI `TestClient` against an **in-memory SQLite** DB (no Postgres needed) by monkey-patching
  `app.database` and every router's `get_db`. `app/tests/test_runner.py` is a hand-rolled runner
  (`@suite`/`@test` decorators, `seed_minimal()` helper). Run this to validate changes.
- **`python run_tests.py`** — a smoke script that hits a **live** server on `:8000`. Requires the
  server + Postgres running and an admin registered via `POST /auth/register` first.

When adding a router that the SQLite tests touch, add its module to the patch loop in
`app/tests/conftest.py`, or its `get_db` won't be overridden and it will hit Postgres.

## Architecture (the parts that span files)

**Generation pipeline.** `POST /generate` (`app/router/generate.py`) → `Scheduler.run()`
(`app/engine/scheduler.py`) creates a `TimetableGeneration`, then for each requested instance runs
`GreedySolver.solve()` (`app/engine/solvers/greedy_solver.py`), which proposes `SlotCandidate`s that
`ConstraintChecker` (`app/engine/constraint_checker.py`) validates before commit. Generation is
**synchronous** — it blocks the HTTP request (async/Celery is a future phase).

**Profiles are the solver's input contract.** A `TimetableProfile` bundles resources
(`profile_resources`: rooms/faculty/groups/subjects), typed parameters (`profile_parameters`, stored
as strings + a `param_type` tag the solver casts), and constraints. The solver only sees resources
attached to the profile — nothing global.

**`subject_assignments` drives what gets scheduled.** This table is the who-teaches-what-to-which-
group triad. The solver expands each assignment into `weekly_hours` sessions and schedules those. If
a subject in the profile has no assignment, it produces zero sessions. This is the single source of
truth the greedy solver reads instead of assuming every teacher teaches every subject.

**`CollegeSettings` is a singleton (id=1).** Auto-created on app startup and lazily by
`get_settings()` (`app/services/settings_service.py`). Boolean feature flags gate optional solver
behavior (e.g. `allow_cross_dept_subjects` — cross-department sessions are dropped when off), and
`config_json` holds arbitrary tunables (e.g. `max_cross_dept_per_day`, read inside the constraint
checker).

**Cross-timetable safety.** `Scheduler._load_published_conflicts()` builds per-resource reserved
sets — `{"faculty"|"room"|"group": {(id, day, slot)}}` — from every `PUBLISHED` instance across all
generations, and `ConstraintChecker._check_published_conflicts()` refuses to reuse them. The sets are
split per resource deliberately: a combined `(faculty, room, group, day, slot)` tuple would only
block an identical five-way match and miss the real conflicts (same teacher, different room, etc.).

**Instance lifecycle.** `DRAFT → SELECTED → PUBLISHED → ARCHIVED` (`app/router/instances.py`).
Publishing an instance archives previously published instances of the *same* generation; published
instances from *other* generations remain live and feed cross-timetable reservations.

**Auth.** JWT (`python-jose`) with **bcrypt used directly** in `app/utils/auth.py`. Do **not**
reintroduce `passlib`: passlib 1.7.4 is incompatible with modern bcrypt (≥4.1) and silently makes
every password hash/verify raise. The JWT payload carries `admin_id`; every mutation endpoint depends
on `get_current_admin`.

## Conventions

- **One file per domain entity** across `app/models/`, `app/schemas/`, `app/router/`. Routers expose
  a module-level `router: APIRouter` and are mounted in `app/main.py`. Models inherit `Base`
  (`app/database.py`) and use `mapped_column`; schemas split `Create`/`Update`/`Response`.
- **Registering a new table:** define the model, export it from `app/models/__init__.py` (so
  `Base.metadata` and Alembic autogenerate see it), then create a migration. The Alembic history is a
  single linear chain (`aeaadc4f2374 → e47081302c4e → 0d633dc08f98 → 0f8db8a263c5 → e5f8a91c0d4e →
  b7d9f2a1c3e4 → c8e1a4b6d2f7 → d3f5a7c9e1b2 → e9f4a2b6d8c0`).
- There are **22 tables** (older docs saying "21" predate `audit_logs`).
- No linter/formatter is enforced; PEP 8, 4-space indent. Commits follow the standing rules below.

## Git & commits (standing rules)

This repo is destined to become public, so the git log is part of the artifact — commit accordingly.

1. **Impersonal, factual messages.** Describe what changed and why, in the repository's voice.
   Never narrate the session — no "the user said…", "as requested…", "we decided…", "per our
   discussion". Subject ≤ ~70 chars; body explains the *why*.
2. **Many small, focused commits.** Split by concern, not by session — one logical change per
   commit (migration / worker / docs / tests as separate commits). Never one massive end-of-session
   commit. If a message needs bullets to list unrelated changes, it should have been several commits.
3. **Stage in logical chunks** (`git add <specific paths>` per commit), not `git add -A` once.

## Reference docs

`documentation/` holds the deeper design material: `timetable-generator-architecture.md` (schema +
endpoint + solver blueprint), `plan.md` (phased roadmap), `progress.md` (feature checklist), and
`AGENTS.md` (contributor guide). `rough_plan.md` is a private, gitignored scratchpad
kept locally only; it is not part of the repository. Treat the code as ground truth
where these disagree.

## ⚠️ Keep the architecture doc in sync with the code (mandatory)

When you add or change a feature (a table, endpoint, engine rule, parameter, or flag), update
`documentation/timetable-generator-architecture.md` **in the same change** — schema in §3, endpoints
in §4, engine in §5, parameters in §8. The blueprint must not drift from the code. Also update
`plan.md`/`progress.md` checkboxes. (The architecture doc still carries pre-pivot framing — it says
"MySQL" and "module for an ERP"; the project is now standalone on PostgreSQL, so correct stale bits
you touch.)
