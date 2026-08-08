<div align="center">

# Timetable Generator — Constraint-Driven Scheduling

*A standalone scheduling service for colleges and similar institutions.
Manage rooms, faculty, student groups, and subjects; define reusable
profiles; let the solver produce ranked candidate timetables; publish one.*

<p>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="#technology-stack"><img src="https://img.shields.io/badge/stack-FastAPI%20%C2%B7%20PostgreSQL%20%C2%B7%20OR--Tools-009688.svg?style=flat-square" alt="Stack: FastAPI · PostgreSQL · OR-Tools"></a>
  <a href="#roadmap"><img src="https://img.shields.io/badge/status-active%20development-orange.svg?style=flat-square" alt="Status: Active development"></a>
</p>

<p>
  <a href="#overview">Overview</a> ·
  <a href="#features">Features</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#roadmap">Roadmap</a> ·
  <a href="#documentation">Documentation</a>
</p>

</div>

> **Current state.** Greedy and OR-Tools (CP-SAT) solvers are operational;
> the data-driven constraint registry, soft-constraint scoring, and
> cross-timetable safety are shipped. The architecture blueprint in
> [`documentation/timetable-generator-architecture.md`](documentation/timetable-generator-architecture.md)
> is the source of design truth and the authoritative status tracker.

---

## Table of contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Generating a timetable](#generating-a-timetable)
- [Exports](#exports)
- [Project layout](#project-layout)
- [Testing](#testing)
- [Operations](#operations)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Documentation](#documentation)
- [License](#license)

---

## Overview

The service is a **standalone product**, not a module of a larger ERP. It
owns its authentication, schema, audit trail, and publishing workflow. One
engine drives seven timetable kinds — class, faculty, room utilization,
event / seminar, industry program, exam, and lab — sharing the same resource
pool and the same hard/soft constraint model.

A generation run consumes a **profile** (a saveable bundle of resources,
typed parameters, and constraints) and emits **N candidate instances**. An
admin reviews them, selects one, and publishes. Cross-timetable reservations
are loaded at the start of every run from every currently published
instance, so a new timetable can never overlap a live one.

---

## Features

### Scheduling engine
- **Two solvers.** A deterministic greedy solver (default, most-constrained
  first) and Google OR-Tools CP-SAT with a 5-second class-level timeout.
  Select via the `algorithm` field on `POST /generate`.
- **Multi-instance diversity.** Instance #1 is a deterministic baseline;
  later instances are re-seeded and accepted only when their fingerprint
  clears a Hamming-distance threshold, so candidates are visibly different.
- **Soft-constraint scoring.** Active soft rules are weighted into a single
  `instance.soft_score ∈ [0, 1]` (higher is better) and the best across a
  generation is recorded on the generation row.

### Constraint model
- **Hard rules** are inviolable; generation fails if they are broken. The
  registry (`app/engine/constraint_registry.py`) dispatches profile
  constraints by `config_json`. Structural rules (double-booking, capacity,
  cross-timetable safety, faculty load caps, same-subject-per-day,
  cross-department cap) are always on.
- **Soft rules** are scored and weighted. Shipped: `TEACHER_PREFERS_MORNING`,
  `MINIMIZE_STUDENT_FREE_SLOTS`. The catalog holds additional types that
  are not yet wired.
- **`ConstraintType` is a string column**, not a DB enum. New rules can be
  added without a migration.

### Resource & profile management
- **21-table schema** over a single linear Alembic chain
  (`aeaadc4f2374 → d3f5a7c9e1b2`).
- **Subject assignments** are the solver's input: `(subject, faculty,
  group, weekly_hours, load_share)`. A subject with no assignment produces
  zero sessions.
- **Profiles** carry resources, typed parameters, hard rules, and soft
  rules. The solver only sees what a profile declares — nothing global.
- **College settings singleton** (`id=1`) for feature flags
  (`allow_cross_dept_subjects`, `enable_soft_constraint_scoring`, …) and a
  free-form `config_json` for engine tunables.
- **CSV bulk import** for rooms, faculty, groups, and subjects.

### Lifecycle & operations
- **Instance states.** `DRAFT → SELECTED → PUBLISHED → ARCHIVED`.
  Publishing archives the previously published sibling of the *same*
  generation; published instances from other generations remain live and
  feed the next run's reservations.
- **Manual override.** `PATCH /instances/{id}/slots/{slot_id}` writes
  `is_manual_override=true` plus a free-text `override_reason` for audit
  traceability. *Re-validation against the checker is a tracked TODO.*
- **Audit trail.** A global HTTP middleware writes an `audit_logs` row for
  every `POST | PUT | PATCH | DELETE`, with `admin_id` decoded from the JWT,
  `status_code`, and an 8-char `X-Request-ID` correlation token.
- **Annual reset.** `POST /reset` archives published instances to history
  and clears profile state for `FULL_YEAR` or `PROFILE_SPECIFIC`; a
  `timetable_reset_log` row records every reset.
- **Health endpoint.** `GET /health` reports liveness and PostgreSQL
  reachability for deployment monitors.

---

## Architecture

```
HTTP request
    │
    ▼
FastAPI router ──── auth/JWT ──── get_current_admin
    │
    ▼
SQLAlchemy 2.0 ORM ─── PostgreSQL 15 (Alembic migrations)
    │
    ▼
Engine layer
    ├── Scheduler.run()           # orchestrates one generation
    │     ├── _load_published_conflicts()   # per-resource reserved sets
    │     └── Solver.solve() × N attempts
    │           ├── GreedySolver             # deterministic, fast
    │           └── ORToolsSolver            # CP-SAT, 5s timeout
    ├── ConstraintChecker         # gates each candidate
    │     ├── structural rules (inline)
    │     └── HARD_CONSTRAINT_REGISTRY       # @hard_rule decorators
    └── Scorer                    # weighted soft score → instance.soft_score
    │
    ▼
TimetableGeneration → TimetableInstance(s) → TimetableSlot(s)
```

Cross-timetable reservations live in two coordinated places:
`Scheduler._load_published_conflicts()` builds three per-resource sets —
`faculty`, `room`, `group` — keyed by `(id, day_of_week, slot_number)`.
Splitting per resource (rather than a single five-way tuple) is what makes
"same teacher, different room" a real conflict rather than a missed one.

---

## Technology stack

| Layer            | Choice                                                           |
|------------------|------------------------------------------------------------------|
| Web framework    | FastAPI + Starlette                                              |
| ORM              | SQLAlchemy 2.0 (mapped-column models)                            |
| Database         | PostgreSQL 15 via Docker                                         |
| Migrations       | Alembic (single linear chain)                                    |
| Solver           | Google OR-Tools CP-SAT (`ortools`) + a deterministic greedy solver |
| Auth             | JWT (`python-jose`, HS256) with bcrypt (used directly)          |
| Validation       | Pydantic + pydantic-settings                                     |
| Exports          | ReportLab (PDF), stdlib `csv` (CSV), hand-written RFC 5545 (iCal)|
| Observability    | Structured request logging, global audit middleware             |
| Tests            | Hand-rolled in-process runner over FastAPI `TestClient` + SQLite |
| Packaging        | [`uv`](https://github.com/astral-sh/uv) (`pyproject.toml`)       |

---

## Prerequisites

- Python **3.11+**
- [`uv`](https://github.com/astral-sh/uv) (dependency manager)
- Docker + Docker Compose (for PostgreSQL)

> `passlib` is intentionally **not** used — passlib 1.7.4 is incompatible
> with modern bcrypt (≥ 4.1) and silently raises on every hash/verify. This
> project calls `bcrypt` directly.

---

## Quick start

```bash
# 1. Clone & enter the repo
git clone https://github.com/Deepnar/timetable-generator.git
cd timetable-generator

# 2. Copy environment defaults and edit secrets
cp .env.example .env
# → set SECRET_KEY to a strong random string in production

# 3. Install dependencies into a managed .venv
uv sync

# 4. Start PostgreSQL (host port 5433 → container 5432)
docker compose -f docker/docker-compose.yml up -d

# 5. Apply migrations
uv run alembic upgrade head

# 6. Run the dev server
uv run uvicorn app.main:app --reload --port 8000
```

The interactive OpenAPI UI is at <http://localhost:8000/docs>.

### Create your first admin and log in

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"name":"Admin","email":"admin@example.com","password":"changeme"}'

# Login → JWT
curl -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"changeme"}'
```

Use the returned bearer token on the **Authorize** button in `/docs` or in
the `Authorization: Bearer …` header on subsequent requests.

---

## Configuration

Settings are loaded by `pydantic-settings` from environment variables /
`.env`. The relevant keys:

| Variable                    | Purpose                                | Example                      |
|-----------------------------|----------------------------------------|------------------------------|
| `DB_HOST`                   | PostgreSQL host                        | `localhost`                  |
| `DB_PORT`                   | PostgreSQL port (host side)            | `5433`                       |
| `DB_USER` / `DB_PASSWORD`   | PostgreSQL credentials                 | `postgres` / `postgres_secret` |
| `DB_NAME`                   | Database name                          | `timetable_db`               |
| `SECRET_KEY`                | JWT signing key — **rotate in prod**   | strong random string         |
| `ALGORITHM`                 | JWT algorithm                          | `HS256`                      |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime                       | `60`                         |

PostgreSQL runs on host port **5433**, not 5432 (`docker/docker-compose.yml`
maps `5433:5432`). The `.env` value of `DB_PORT` is what matters at runtime.

---

## Generating a timetable

```bash
curl -X POST http://localhost:8000/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "profile_id": 1,
    "timetable_type": "CLASS",
    "academic_year": "2025-26",
    "semester": 5,
    "instances_requested": 3,
    "algorithm": "GREEDY"
  }'
```

**The endpoint is synchronous by default** — it returns when the solver finishes,
with the generation row plus its candidate instances. To move long runs off the
HTTP request, set `ASYNC_GENERATION=true` in `.env` (with Redis + a Celery worker
running, see [Architecture doc §7.1](documentation/timetable-generator-architecture.md)):
`POST /generate` then returns **202** with a `PENDING` run and the worker completes
it in the background. Status polling lives at `GET /generate/{run_id}/status`
(`PENDING`/`RUNNING`/`COMPLETED`/`FAILED`).

### Lifecycle endpoints

```bash
GET    /instances/{generation_id}              # list candidates
GET    /instances/{instance_id}/slots          # slot detail (ordered by day, slot)
POST   /instances/{instance_id}/select         # SELECTED — records selected_by/_at
POST   /instances/{instance_id}/publish        # PUBLISHED — auto-archives the sibling
PATCH  /instances/{instance_id}/slots/{slot_id} # manual override
```

---

## Exports

All three formats share a single filter layer (`get_filtered_slots`):

```
GET /export/instances/{id}/pdf
GET /export/instances/{id}/csv
GET /export/instances/{id}/ical
    ?group_id=…       one division's schedule
    ?faculty_id=…     one teacher's schedule
    ?year=…           a whole year
    ?department=…     a department
    ?term_start=YYYY-MM-DD     # iCal only — anchor date
    ?term_end=YYYY-MM-DD       # iCal only — optional RRULE UNTIL
```

- **PDF** — landscape A4 wall chart, ReportLab. Renders an empty grid on no
  matches.
- **CSV** — flat row-per-slot export. Returns 404 on no matches.
- **iCal** — RFC 5545 with weekly-recurring `VEVENT`s (`RRULE FREQ=WEEKLY`).
  Imports cleanly into Google Calendar and Outlook.

---

## Project layout

```
app/
├── main.py                      # FastAPI app, middleware, /health
├── config.py                    # pydantic-settings (DB_*, SECRET_KEY, ALGORITHM)
├── database.py                  # SQLAlchemy engine + SessionLocal + Base
│
├── models/                      # SQLAlchemy 2.0 mapped-column models (one per entity)
│   ├── admin.py / audit.py / faculty.py / groups.py / rooms.py
│   ├── subjects.py / subject_assignments.py
│   ├── profiles.py              # profiles, resources, parameters, combinations
│   ├── constraints.py           # hard/soft rules + ConstraintType catalog
│   ├── generation.py            # generations, instances, slots
│   ├── history.py               # archives + reset log
│   └── settings.py              # college_settings singleton
│
├── schemas/                     # Pydantic Create/Update/Response per entity
├── router/                      # APIRouter per entity (one file each)
│
├── engine/
│   ├── scheduler.py             # Scheduler.run() orchestrator
│   ├── constraint_checker.py    # SlotCandidate, ConstraintViolation
│   ├── constraint_registry.py   # HARD_CONSTRAINT_REGISTRY + @hard_rule
│   ├── scorer.py                # SOFT_CONSTRAINT_REGISTRY + score_instance()
│   └── solvers/
│       ├── greedy_solver.py     # default, deterministic
│       └── or_tools_solver.py   # CP-SAT, 5s timeout
│
├── services/
│   ├── settings_service.py      # get_settings() / update_settings()
│   └── export_service.py        # PDF + CSV + iCal, shared filter layer
│
└── tests/                       # conftest.py + hand-rolled @suite/@test runner

alembic/versions/                # single linear chain
docker/                          # docker-compose.yml (Postgres 15)
documentation/                   # architecture blueprint, plan, progress, contributor guide
rough_plan.md                    # local-only brainstorming notes — gitignored, never tracked
```

> `rough_plan.md` exists in your working copy as a private scratchpad for
> half-formed ideas, scratch timelines, and notes that may contain personal
> context. It is intentionally **not** in the repository — see the
> `.gitignore` entry. The architecture blueprint (`documentation/`) is the
> canonical record of design decisions.


One file per domain entity, across `models/`, `schemas/`, and `router/`.
Routers expose a module-level `router: APIRouter` and are mounted in
`app/main.py`. Models inherit `Base` from `app/database.py` and use
`mapped_column`; schemas split `Create`, `Update`, and `Response`.

---

## Testing

Two independent entry points — **pytest is intentionally not used**.

```bash
# Integration suite — FastAPI TestClient over in-memory SQLite.
# No Postgres needed. Patches app.database + every router's get_db.
uv run python -m app.tests

# Smoke script — hits a LIVE server on :8000.
# Requires Postgres + a registered admin.
python run_tests.py
```

When adding a router that the SQLite tests touch, add its module to the
patch loop in `app/tests/conftest.py` — otherwise its `get_db` won't be
overridden and the tests will hit Postgres.

Test guidelines:
- Suites are registered with `@suite("name")`; cases with `@test("…")`.
  See `app/tests/test_settings_and_assignments.py`.
- Use `seed_minimal()` to build a base scenario.
- Prioritise coverage for: router endpoints, engine/solver logic,
  constraint checker, and profiles.

---

## Operations

- **Liveness.** `GET /health` returns `{"status": "ok", "db": "connected"}`
  when PostgreSQL is reachable, `degraded` otherwise.
- **Audit.** Every mutating request is logged to `audit_logs` with the
  resolved `admin_id` (best-effort JWT decode) and an 8-char `X-Request-ID`
  correlation token. The audit write is wrapped in try/except so it never
  breaks a request.
- **Migration safety.** Alembic history is a single linear chain; branch
  work should `alembic upgrade head` against a clean database before
  opening a PR. New tables must be exported from `app/models/__init__.py`
  so `Base.metadata` and Alembic autogenerate see them.
- **Password hashing.** `app/utils/auth.py` calls `bcrypt` directly — do
  **not** reintroduce `passlib`.

---

## Roadmap

Drawn from `documentation/timetable-generator-architecture.md` §9:

1. **Async generation + WebSocket** for `POST /generate` (biggest UX blocker).
2. **Wire the remaining `profile_parameters` to the engine** — many keys
   are stored but not read.
3. **Fold soft scoring into the CP-SAT objective** (currently a post-hoc
   ranker).
4. **Objective-based instance variation** — replace seed-only diversity
   with "best / minimise teacher gaps / minimise student gaps / random".
5. **Frontend** (Next.js SPA) against this API.
6. **Notification service** — email + push on publish.
7. **RBAC** — HOD / Teacher / Student user classes.
8. **Genetic solver** — only if CP-SAT still leaves real departments
   unsolved.

`SEMESTER` reset is accepted by the schema but currently a no-op; profile
combination resolution and override re-validation are tracked TODOs.

---

## Contributing

- Branch off `main`, keep commits small and imperative-lowercase
  (`add iCal export`, `wire max_daily_load_teacher`, …).
- One file per domain entity across `models/`, `schemas/`, `router/`.
- No linter is enforced; PEP 8, 4-space indent. `ruff check app/` is
  recommended locally.
- Whenever you add or change a table, endpoint, engine rule, parameter, or
  flag, update
  [`documentation/timetable-generator-architecture.md`](documentation/timetable-generator-architecture.md)
  in the same change. The blueprint must not drift from the code.
- Do not include AI attribution (`Co-Authored-By`, etc.) in commits or PR
  bodies.

---

## Documentation

| File | Purpose |
|------|---------|
| [`documentation/timetable-generator-architecture.md`](documentation/timetable-generator-architecture.md) | The blueprint — schema, endpoints, engine, parameters, roadmap. **The** reference. |
| [`documentation/plan.md`](documentation/plan.md) | Phased implementation roadmap. |
| [`documentation/progress.md`](documentation/progress.md) | Living feature checklist. |
| [`documentation/AGENTS.md`](documentation/AGENTS.md) | Contributor guide. |
| [`CLAUDE.md`](CLAUDE.md) | Claude Code working notes for this repo. |
| `rough_plan.md` | **Local-only scratchpad** for brainstorming — gitignored by design, never committed. |

> Where documentation disagrees with the code, **the code is the source of
> truth.**

---

## License

MIT — see [`LICENSE`](LICENSE). Copyright © 2026 Deepesh Sonar.
