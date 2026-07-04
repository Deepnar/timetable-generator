# Repository Guidelines

## What This Module Does

This is the **Timetable Generator** — a multi-domain scheduling engine that produces and manages seven timetable types: Class, Faculty, Room Utilization, Event/Seminar, Industry Program (IP), Exam, and Lab schedules. All types share the same constraint engine and resource pool to guarantee zero cross-timetable conflicts.

The full architectural blueprint lives at `documentation/timetable-generator-architecture.md`. Refer to it for database schema definitions, endpoint contracts, solver strategy details, and the implementation roadmap.

---

## Core Concepts

| Concept | Description |
|---|---|
| **Resources** | Everything schedulable — faculty, rooms, student groups, equipment |
| **Constraints** | Hard (inviolable; generation fails) and Soft (preferences scored & weighted) |
| **Profiles** | Named, saveable bundles of resources + constraints + parameters (think "presets" like *CS Dept Full Semester*) |
| **Instances** | Every generation run produces multiple candidate timetables; the admin picks one — no auto-commit |

---

## Project Structure & Module Organization

```
app/
├── main.py                       # FastAPI entry point, router mounting, CORS
├── config.py                     # Pydantic Settings loaded from .env
├── database.py                   # SQLAlchemy engine + session factory (MySQL via PyMySQL)
│
├── models/                       # SQLAlchemy ORM models — one file per entity domain
│   ├── rooms.py                  # Rooms + RoomBlackout
│   ├── faculty.py                # Faculty + FacultyAvailability
│   ├── groups.py                 # StudentGroups
│   ├── subjects.py               # Subjects + SubjectHours
│   ├── profiles.py               # TimetableProfile + profile_resources + profile_parameters
│   ├── constraints.py            # Hard/Soft constraint models
│   ├── generation.py             # Generation runs, Instances, Slots
│   ├── history.py                # Archived timetable snapshots
│   └── admin.py                  # Admin user model (auth)
│
├── schemas/                      # Pydantic request/response models mirroring each domain
├── router/                       # FastAPI routers — one per resource or feature
│   ├── auth.py                   # JWT login/token refresh
│   ├── generate.py               # POST /generate  (core scheduling endpoint)
│   ├── instances.py              # Instance selection, view, diff
│   └── ...                       # rooms, faculty, groups, subjects, etc.
│
├── engine/                       # Scheduling engine — the heart of the system
│   ├── scheduler.py              # Orchestrator: validates profile → runs solver → saves slots
│   ├── constraint_checker.py     # Hard constraint validator (before each slot commit)
│   └── solvers/
│       └── greedy_solver.py      # Greedy algorithm (fast previews, current default)
│       # → Future: or_tools_solver.py (OR-Tools CP-SAT — primary solver)
│       # → Future: genetic_solver.py (GA for large-scale diversity)
│
├── services/                     # Business logic helpers
│   └── export_service.py         # PDF/CSV export
├── tasks/                        # Async jobs (future: Celery + Redis)
└── utils/                        # Cross-cutting utilities
    └── auth.py                   # JWT creation, verification, password hashing

alembic/                          # DB migrations (configured via alembic.ini)
test_data/                        # Sample CSV fixtures for bulk import
```

---

## Build, Test, and Development Commands

This project uses **[uv](https://github.com/astral-sh/uv)** for fast dependency management and virtual environments.

```bash
# 1. Install dependencies & create the managed .venv
uv sync

# 2. Run the dev server (auto-reload on file changes)
uv run uvicorn app.main:app --reload --port 8000

# 3. Add a new dependency
uv add <package_name>

# 4. Generate an Alembic migration
uv run alembic revision --autogenerate -m "describe change"

# 5. Apply pending migrations
uv run alembic upgrade head
```

> The API is reachable at `http://localhost:8000`. Interactive Swagger docs are at `/docs`.

---

## Coding Style & Naming Conventions

- **Indentation**: 4 spaces. Follow [PEP 8](https://peps.python.org/pep-0008/).
- **Naming**: snake_case for modules, variables, and functions; PascalCase for classes and Pydantic schemas.
- **One file per domain entity**: `app/models/<entity>.py`, `app/schemas/<entity>.py`, `app/router/<entity>.py`.
- **Routers** must expose a `router: APIRouter` object (imported by `app/main.py`).
- **Models** inherit from `Base` (defined in `app/database.py`). Use `mapped_column` for column definitions.
- **Schemas** separate `Create`, `Update`, and `Read` variants where applicable.
- No linter/formatter is currently enforced. Running `ruff check app/` or `flake8 app/` locally is recommended.

---

## Testing Guidelines

No test suite exists yet. When adding tests:

- Use **pytest** (`uv add --dev pytest`).
- Place files under `app/tests/test_<module>.py`.
- Name functions `test_<action>_<expected_outcome>` (e.g., `test_create_room_success`, `test_constraint_violation_detected`).
- Prioritize coverage for: router endpoints, engine/solver logic, constraint checker, and profile management.

```bash
uv run pytest app/tests/ -v
```

---

## Commit & Pull Request Guidelines

### Commits

Follow the **imperative lowercase** style established in Git history:

```
add CORS middleware
greedy solver working, auth fixed, bcrypt compatible
PDF and CSV export for timetable instances
```

- First line under 72 characters.
- Reference issue numbers in the body when applicable.

### Pull Requests

Include a brief description of changes. If the PR introduces new DB tables or schema changes, **note the Alembic migration**. If it touches the engine or solver logic, describe the algorithmic impact.

---

## Implementation Status vs. Roadmap

The architecture blueprint defines five phases. Current state:

| Phase | Scope | Status |
|---|---|---|
| **1 — Foundation** | Project structure, DB tables (18), CRUD APIs, auth, CSV import | ✅ Largely complete |
| **2 — Greedy Engine** | Greedy scheduler, hard constraint checker, sync `/generate` | ✅ Complete |
| **3 — Real Solver** | OR-Tools CP-SAT, soft constraint scorer, multi-instance diversity, Celery async | ⏳ Planned |
| **4 — Profile System** | Profile combine/resolve, profile shift, annual reset workflow | ⏳ Planned |
| **5 — Enterprise** | Manual override + re-check, cross-timetable conflicts, iCal export, notifications, versioning | ⏳ Planned |

When contributing to future phases, always reference the architecture doc for the endpoint contract, data model expectations, and algorithm details.

---

## Security & Configuration Tips

- **Never commit `.env`**. Copy from `.env.example` and set your own values.
- `SECRET_KEY` must be a strong random string — rotate in production.
- The database uses MySQL via PyMySQL; ensure credentials match your server configuration.
- This service runs as a standalone FastAPI microservice (default port `:8000`). The main ERP backend (Node.js) communicates with it over HTTP.
