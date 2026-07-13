# Progress Tracker — Timetable Generator

This document provides a living status of every feature, table, and improvement discussed in the architecture blueprint (`documentation/timetable-generator-architecture.md`) and the session notes (`rough_plan.md`). 

**Current State:** `v0.greedy-complete` (Foundation + Greedy Engine phase fully implemented).
**Project Scope:** This is a **standalone full-stack enterprise application**, not a microservice. It includes the backend API, PostgreSQL database via Docker, and will soon integrate a frontend interface for college admins.

---

## 🛠️ Recently Fixed (cross-check pass)

These were marked "complete" in earlier docs but were actually broken; now fixed and covered by the `python -m app.tests` suite (13/13 passing):

- **Auth was fully broken at runtime** — `passlib 1.7.4` is incompatible with `bcrypt ≥ 5`, so every `hash_password`/`verify_password` raised `ValueError`. `app/utils/auth.py` now calls `bcrypt` directly; `passlib` removed from deps.
- **Cross-timetable contamination fix didn't work** — reservations were bundled into one `(faculty, room, group, day, slot)` tuple, so only an identical 5-way match was blocked. Now split into per-resource sets (`faculty`/`room`/`group` → `{(id, day, slot)}`) and enforced in the constraint checker.
- **`POST /generate` 500'd** — the scheduler never set the `NOT NULL` `instance_number`; now populated per instance.
- **Individual faculty PDF was the full timetable** — `generate_faculty_pdf` filtered the slots then discarded them and re-rendered everything; now renders only that faculty's slots.

New engine capabilities added in the same pass (with tests):
- **Configurable `day_start_time`** profile param (`"HH:MM"`, default `09:00`) — the day no longer starts at a hardcoded 9 AM, so schools/evening programs work too.
- **Faculty load limits enforced** — `max_hours_per_day` / `max_hours_per_week` were stored but ignored by the solver; now hard-checked.

---

## 🔎 Newly Identified (cross-check pass — not yet on the roadmap)

Bugs/gaps found while auditing that `plan.md` does **not** already cover:

- ~~**Room blackout check is effectively dead**~~ — ✅ FIXED: `room_blackouts` now supports recurring **weekday** blackouts (`day_of_week`), which the checker enforces against the recurring templates. Date-specific blackouts still await calendar-date materialization.
- **Faculty availability date-range ignored** — `effective_from`/`effective_to` are never consulted, and they are typed `date | None` yet marked `nullable=False` (contradiction that also breaks CRUD/CSV that omit them).
- **CSV import is not atomic** — each row is `add()`ed and everything is `commit()`ed once at the end; a single integrity error at commit rolls back rows already reported as "inserted". Also `import_rooms` lets `room_code` be `None` against a `NOT NULL UNIQUE` column.
- **Profile combinations are never resolved** — `/profiles/combine` stores members, but `Scheduler`/`GreedySolver` only read a single `profile_id`; generating from a `combination_id` fails. (Loosely Phase 4, but the endpoint currently misleads.)
- **`GET /constraints/types` is a hardcoded string list** that can drift from the `ConstraintType` enum.
- **Read-route auth is inconsistent** — `/settings` GET requires a token, most other GETs don't.

---

## ✅ Completed Features

### Database & Models
- [x] **21 Database Tables**: Migrated via Alembic (rooms, blackouts, faculty, availability, groups, subjects, subject_assignments, college_settings, profiles, parameters, combinations, constraints, generation runs, instances, slots, history, reset log, admin, etc.)
- [x] **SQLAlchemy 2.0 ORM**: Declarative models with `mapped_column` and relationship mappings.
- [x] **Database Migration to PostgreSQL**: Switched from local MySQL to Docker-managed Postgres 15 container.

### Authentication & Security
- [x] **JWT Auth**: Admin login, token refresh, bcrypt password hashing.
- [x] **Protected Routes**: All write/mutation endpoints require valid JWT via `get_current_admin`.
- [x] **CORS Middleware**: Configured for frontend communication (localhost:3000).

### Resource Management (CRUD)
- [x] **Rooms API**: Full CRUD, blackout window management, query param filtering (type, building, capacity).
- [x] **Faculty API**: Full CRUD, availability windows, filtering.
- [x] **Student Groups API**: Full CRUD, hierarchical grouping support, filtering.
- [x] **Subjects API**: Full CRUD, subject-hours mapping, filtering.
- [x] **CSV Bulk Import**: Robust parser for all 4 entities with validation.

### Profiles & Constraints
- [x] **Profile System**: Create/edit profiles, link resources, set parameters.
- [x] **Profile Combinations**: Merge multiple profiles, preview conflict resolution.
- [x] **Constraint CRUD**: Hard and soft constraint tables, weight management, profile scoping.

### Scheduling Engine & Data Mapping (Phase 1)
- [x] **Greedy Solver**: Priority-based assignment with fast execution for previews.
- [x] **Hard Constraint Checker**: Validates room capacity, faculty availability, blackouts, and basic double-booking prevention before committing slots.
- [x] **Subject-Faculty-Group Mapping Table**: `subject_assignments` table created to handle exact mappings, cross-dept subjects, and shared teaching loads (80/20 splits). Greedy solver now reads from this table instead of guessing.
- [x] **Cross-Timetable Contamination Fix**: Scheduler now fetches all `PUBLISHED` slots before running a new generation, preventing double-bookings across separate timetable runs.

### Generation Workflow & Instances
- [x] **Generation Trigger**: `POST /generate` accepts profile/combination, runs solver synchronously.
- [x] **Instance Management**: View generated instances, select a candidate, publish to live system.
- [x] **Manual Slot Override**: Edit individual slots post-generation (`PATCH /instances/{id}/slots/{slot_id}`). ⚠️ *Note: the override is currently saved without re-running the constraint checker — live re-validation is still TODO (see Engine improvements below).*

### Exports & History
- [x] **PDF Export**: Full timetable grid generation using ReportLab.
- [x] **CSV Export**: Data portability for all generated slots.
- [x] **History & Reset**: Archive published timetables, view past snapshots, annual reset workflow (non-destructive).

### API Utilities
- [x] **Query Param Filtering**: Applied across all primary GET routes.
- [x] **Dependency Management Migrated to `uv`**: Removed old `pip`/`requirements.txt` setup; using modern `pyproject.toml`.

---

## ⏳ Planned / Pending Features

### 🔴 Critical Missing (Blockers for Real Usage)
- [x] **College Settings / Feature Flags Table** *(largely done)*
  - `college_settings` model, migration, `GET/PUT /settings/` endpoints, and the `get_settings()` singleton service are all in place; the solver honors `allow_cross_dept_subjects` and the checker reads `config_json.max_cross_dept_per_day`.
  - *Remaining:* wire the remaining flags (`enable_lab_batches`, `enable_soft_constraint_scoring`) into their respective features as those land.

### 🟠 Engine & Solver Improvements
- [x] **Dynamic Constraint Checker** *(foundation)* — `app/engine/constraint_registry.py` dispatches profile `hard_constraints` (by `config_json`) to registered validators; `constraint_type` is now a plain string so new rules skip schema migrations. Core structural checks stay inline (see plan.md Phase 2).
- [ ] **New Constraint Types** *(3 of 5 registry rules done)*
  - Done: `SUBJECT_TIME_PREFERENCE`, `MAX_CONSECUTIVE_SAME_TEACHER`, `TEACHER_YEAR_RESTRICTION`.
  - Pending: `LAB_BATCH_ROTATION` (needs lab-batch model), `HOLIDAY_CALENDAR` (weekday-vs-date gap), `DIVISION_START_TIME` (per-division start; global `day_start_time` already works).
- [x] **Soft Constraint Scoring** — `app/engine/scorer.py` registry weights each instance's soft constraints into `instance.soft_score` / `generation.score_best_instance` (gated by `enable_soft_constraint_scoring`). Ships `TEACHER_PREFERS_MORNING`, `MINIMIZE_STUDENT_FREE_SLOTS`.
- [x] **OR-Tools CP-SAT Solver** — `app/engine/solvers/or_tools_solver.py`, selectable via `algorithm="OR_TOOLS"`. Domain-prunes with the shared `ConstraintChecker` and adds relational CP-SAT constraints; greedy remains the default preview solver. *(Next: use the soft scorer as a weighted objective; add a diversity filter.)*
- [x] **Diversity Filter** — instance #1 is a deterministic baseline; later instances are re-seeded (greedy shuffles search order, OR-Tools varies `random_seed`) and accepted only if their Hamming distance from earlier instances clears a threshold (retries otherwise). Fixes the "3 identical instances" problem.

### 🟡 Exports, Notifications & Polish
- [ ] **Filtered Exports**
  - Export by division, individual teacher, year, or department.
- [ ] **iCal (.ics) Export**
  - Calendar file for Google Calendar / Outlook integration.
- [ ] **Email Notifications on Publish**
  - SMTP setup, trigger emails to faculty (personal PDF), HOD (summary), and class incharges.
- [ ] **Redis Integration**
  - Cache frequent queries, rate limiting, session management, and generation conflict locking.
- [ ] **Async Generation (Celery)**
  - Move long-running solver tasks out of the HTTP request cycle.
- [ ] **API Polish**
  - Pagination (`page/limit`), global error middleware, request logging/audit trail, `GET /health`, API versioning (`/api/v1/`).

### 🟢 Full Stack Frontend Development (Next.js / React)
*This is now a core part of this project, not an external consumer.*
- [ ] **Frontend Initialization**: Setup Next.js app within the full-stack deployment pipeline.
- [ ] **Auth & Dashboard**: Login page, JWT handling, stats view, quick actions.
- [ ] **Resource Management Pages**: Tables with search/filter, CSV uploads, CRUD modals.
- [ ] **Master Assignment Grid**: UI to map teachers → subjects → divisions.
- [ ] **Profile & Constraint Builder**: Visual form for profiles and dynamic constraints.
- [ ] **Generation Viewer**: Side-by-side instance comparison grid, progress bar for async runs.
- [ ] **Instance Editor**: Click-to-edit slots with live conflict re-checking.

### 🔵 Deployment & Final Polish
- [ ] **Full Stack Dockerization**: `Dockerfile` + top-level `docker-compose.yml` (App, Frontend, PostgreSQL, Redis). *(Today `docker/docker-compose.yml` runs only Postgres.)*
- [ ] **README & Docs**: Setup guide, architecture diagram link, API examples.
- [ ] **Historical Data Import**: Upload past semesters' timetables for pattern reference.
- [ ] **ML Preference Learning (Phase 2)**: Learn from manual overrides to suggest constraints automatically.

---

> **How to use this file:** Check off items (`- [x]`) as they are merged into `main`. Use the color coding to prioritize your next sprint (🔴 Critical → 🟠 Engine → 🟡 Polish).
