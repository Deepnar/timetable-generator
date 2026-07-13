## 🚀 Session Initialization

Before doing anything else, you MUST activate the virtual environment. All dependencies are managed by `uv`.

```bash
source .venv/bin/activate
```

Ensure this is active before running any Python scripts, migrations, or the FastAPI server. Never use `pip`—use `uv add`, `uv sync`, and `uv run` exclusively.

---

# Repository Guidelines

## What This Application Does

This is the **Enterprise Timetable Management System** — a standalone, full-stack application that produces and manages seven timetable types: Class, Faculty, Room Utilization, Event/Seminar, Industry Program (IP), Exam, and Lab schedules. It replaces manual spreadsheet-based scheduling with a constraint-driven engine that guarantees zero cross-timetable conflicts across the entire institution.

### Project Overview & Current Context
This project is a **complete full-stack application** (Backend + Database + Frontend). It is built on **FastAPI**, **SQLAlchemy 2.0**, and uses a **PostgreSQL database managed via Docker**. It is NOT a microservice for another ERP; it is the primary scheduling product itself.

**Current Development State:**
The backend system is at the **`v0.greedy-complete`** checkpoint. 
- **Completed:** The foundational backend is fully built. This includes 21 database tables, full CRUD for all resources (rooms, faculty, groups, subjects), JWT authentication, CSV bulk imports, a dynamic profile/constraint system, a greedy constraint-based solver, synchronous timetable generation, manual slot overrides, PDF/CSV exports, and history/reset workflows.
- **Dependency Management:** Fully migrated to `uv` (`pyproject.toml`). The old `pip` and `requirements.txt` workflow has been retired.

**Next Major Goal:**
We are moving into **Phase 1**: fixing the missing Subject-Faculty-Group mapping table, implementing cross-timetable conflict prevention, and adding college-wide feature flags before tackling advanced solvers (OR-Tools) and building the full-stack frontend.

---

## Core Concepts

| Concept | Description |
|---|---|
| **Resources** | Everything schedulable — faculty, rooms, student groups, equipment |
| **Constraints** | Hard (inviolable; generation fails) and Soft (preferences scored & weighted) |
| **Profiles** | Named, saveable bundles of resources + constraints + parameters (think "presets" like *CS Dept Full Semester*) |
| **Instances** | Every generation run produces multiple candidate timetables; the admin picks one — no auto-commit |

---

## 📚 Essential Reference Files

To fully understand the architecture, current progress, and future plans, please read these files:

1.  **`documentation/timetable-generator-architecture.md`** 
    The master architectural blueprint. It contains the complete database schema designs, endpoint contracts, solver strategies (Greedy vs OR-Tools), and the overall system vision.
2.  **`documentation/plan.md`** 
    The phased implementation roadmap. It outlines exactly how to bridge the gap from the current greedy engine to the final enterprise-grade full-stack application.
3.  **`documentation/progress.md`** 
    A living feature checklist. Use this to track completed work and identify what is currently blocked or planned.
4.  **`rough_plan.md`** (repo root)
    Raw session notes containing brainstormed ideas, late-night discoveries (like college settings tables), and frontend/API polish requirements.

---

## Project Structure & Module Organization

```
app/
├── main.py                       # FastAPI entry point, router mounting, CORS
├── config.py                     # Pydantic Settings loaded from .env
├── database.py                   # SQLAlchemy engine + session factory (PostgreSQL via psycopg2)
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
docker/                           # Docker configuration for PostgreSQL database
test_data/                        # Sample CSV fixtures for bulk import
```

---

## Build, Test, and Development Commands

This project uses **[uv](https://github.com/astral-sh/uv)** for fast dependency management and virtual environments. The database is managed via **Docker Compose**.

```bash
# 1. Install dependencies & create the managed .venv
uv sync

# 2. Start the PostgreSQL database container
cd docker && docker compose up -d

# 3. Run the dev server (auto-reload on file changes)
uv run uvicorn app.main:app --reload --port 8000

# 4. Add a new dependency
uv add <package_name>

# 5. Generate an Alembic migration
uv run alembic revision --autogenerate -m "describe change"

# 6. Apply pending migrations
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

The project ships a **custom in-process test runner** (pytest is intentionally *not* used and not
installed). `app/tests/conftest.py` runs the FastAPI app against an in-memory SQLite DB, so no
Postgres is needed.

```bash
uv run python -m app.tests     # full integration suite (currently 13/13 passing)
python run_tests.py            # optional smoke test against a LIVE server on :8000
```

When adding tests:

- Register a suite with `@suite("name")` and individual cases with `@test("...")` in
  `app/tests/test_<module>.py` (see `test_settings_and_assignments.py`). Use the `seed_minimal()`
  helper to build a base scenario.
- If a new router must run under the SQLite tests, add its module to the `get_db` patch loop in
  `app/tests/conftest.py`.
- Prioritize coverage for: router endpoints, engine/solver logic, constraint checker, and profiles.

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
| **1 — Foundation** | Project structure, DB tables (21), CRUD APIs, auth, CSV import, subject assignments, college settings | ✅ Largely complete |
| **2 — Greedy Engine** | Greedy scheduler, hard constraint checker, sync `/generate`, cross-timetable conflict prevention | ✅ Complete |
| **3 — Real Solver** | OR-Tools CP-SAT, soft constraint scorer, multi-instance diversity, Celery async | ⏳ Planned |
| **4 — Profile System** | Profile combine/resolve, profile shift, annual reset workflow | ⏳ Planned |
| **5 — Enterprise** | Manual override **re-check** (override endpoint exists; re-validation TODO), iCal export, notifications, versioning | ⏳ Planned |

When contributing to future phases, always reference the architecture doc for the endpoint contract, data model expectations, and algorithm details.

---

## Security & Configuration Tips

- **Never commit `.env`**. Copy from `.env.example` and set your own values.
- `SECRET_KEY` must be a strong random string — rotate in production.
- The database is now managed via Docker Compose (`docker/docker-compose.yml`) using PostgreSQL 15. Ensure the container is running before starting the FastAPI server.
- This is a **standalone full-stack application**. It handles its own authentication, database connection, and frontend serving (when implemented).
