# Progress Tracker — Timetable Generator

This document provides a living status of every feature, table, and improvement discussed in the architecture blueprint (`documentation/timetable-generator-architecture.md`) and the session notes (`rough_plan.md`). 

**Current State:** greedy and OR-Tools (CP-SAT) solvers working, data-driven constraint registry, soft-constraint scoring; async generation and a frontend are planned.
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
- ~~**Faculty availability date-range ignored**~~ — ✅ FIXED: `effective_from`/`effective_to` are now nullable (migration `e9f4a2b6d8c0`) so timeless windows can be created via CRUD/CSV, and the checker consults them against each slot's materialized date. The solver anchors the weekly template with the new **`term_start`** profile parameter (see architecture §8.8) and stamps `TimetableSlot.slot_date`; a date-bounded window only blocks the week it covers, and a window with no bounds stays timeless.
- ~~**CSV import is not atomic**~~ — ✅ FIXED: `/import/{rooms,faculty,groups,subjects}` are now **all-or-nothing**. Every row is validated up front (required fields, duplicates within the file AND against the DB); any invalid row rejects the whole upload with `422` and `inserted=0`, so the DB never ends up holding rows the response didn't report. `import_rooms` also now requires a non-empty `room_code`.
- ~~**Profile combinations are never resolved**~~ — ✅ FIXED: `ProfileResolver` (`app/engine/profile_resolver.py`) merges combination members into an effective profile before solving — resources unioned (de-dup by `(resource_type, resource_id)`), parameters resolved with the **highest-weight member winning collisions**, hard/soft constraints merged from every member plus globals. `POST /generate` with `combination_id` now schedules all members' resources; the generation row stores `combination_id` with `profile_id=NULL`. `POST /profiles/combine` validates member existence and weights length; slot-override re-validation re-resolves the combination too. See architecture §6.2.
- ~~**`GET /constraints/types` is a hardcoded string list**~~ — ✅ FIXED: the endpoint now derives its hard/soft lists from `HARD_CONSTRAINT_TYPES` / `SOFT_CONSTRAINT_TYPES` (defined next to the `ConstraintType` enum), so discovery can never drift from what the Create schemas accept.
- ~~**Read-route auth is inconsistent**~~ — ✅ FIXED: every route now requires a valid admin JWT except `GET /health` and the `/auth/*` endpoints (`register`/`login`). Enforced by one global middleware (`require_auth` in `app/main.py`) instead of a per-route dependency, so a new router/endpoint cannot accidentally be left public; `/docs` and `/openapi.json` are gated too. `get_current_admin` remains only on mutations that need the admin identity. See architecture §4.2 / §7.4.

---

## ✅ Completed Features

### Database & Models
- [x] **21 Database Tables**: Migrated via Alembic (rooms, blackouts, faculty, availability, groups, subjects, subject_assignments, college_settings, profiles, parameters, combinations, constraints, generation runs, instances, slots, history, reset log, admin, etc.)
- [x] **SQLAlchemy 2.0 ORM**: Declarative models with `mapped_column` and relationship mappings.
- [x] **Database Migration to PostgreSQL**: Switched from local MySQL to Docker-managed Postgres 15 container.

### Authentication & Security
- [x] **JWT Auth**: Admin login, token refresh, bcrypt password hashing.
- [x] **Global Auth Gate**: every route requires a valid admin JWT via a single `require_auth` middleware — exempt only `GET /health` and `/auth/*`. Replaced the old "mutations only" posture where all reads were public.
- [x] **CORS Middleware**: Configured for frontend communication (localhost:3000).

### Resource Management (CRUD)
- [x] **Rooms API**: Full CRUD, blackout window management, query param filtering (type, building, capacity).
- [x] **Faculty API**: Full CRUD, availability windows, filtering.
- [x] **Student Groups API**: Full CRUD, hierarchical grouping support, filtering.
- [x] **Subjects API**: Full CRUD, subject-hours mapping, filtering.
- [x] **CSV Bulk Import**: Robust parser for all 4 entities with validation. All-or-nothing (any bad row rejects the file with `422`, `inserted=0`).

### Profiles & Constraints
- [x] **Profile System**: Create/edit profiles, link resources, set parameters.
- [x] **Profile Combinations**: Merge multiple profiles into an effective profile (`app/engine/profile_resolver.py`); resolution happens automatically at generation time — resources unioned, parameters weighted (highest weight wins on collisions), hard/soft constraints merged from every member plus globals (§6.2).
- [x] **Constraint CRUD**: Hard and soft constraint tables, weight management, profile scoping.

### Scheduling Engine & Data Mapping (Phase 1)
- [x] **Greedy Solver**: Priority-based assignment with fast execution for previews.
- [x] **Hard Constraint Checker**: Validates room capacity, faculty availability, blackouts, and basic double-booking prevention before committing slots.
- [x] **Subject-Faculty-Group Mapping Table**: `subject_assignments` table created to handle exact mappings, cross-dept subjects, and shared teaching loads (80/20 splits). Greedy solver now reads from this table instead of guessing.
- [x] **Cross-Timetable Contamination Fix**: Scheduler now fetches all `PUBLISHED` slots before running a new generation, preventing double-bookings across separate timetable runs.

### Generation Workflow & Instances
- [x] **Generation Trigger**: `POST /generate` accepts profile/combination, runs solver synchronously.
- [x] **Instance Management**: View generated instances, select a candidate, publish to live system.
- [x] **Manual Slot Override**: Edit individual slots post-generation (`PATCH /instances/{id}/slots/{slot_id}`). ✅ Overrides are now re-validated by the full constraint checker before saving (a conflict returns 409 and leaves the slot untouched).

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
- [x] **New Constraint Types** *(6 of 7 done)*
  - Done: `SUBJECT_TIME_PREFERENCE`, `MAX_CONSECUTIVE_SAME_TEACHER`, `TEACHER_YEAR_RESTRICTION`, `LAB_BATCH_ROTATION` (pins a group/lab-batch to weekdays via `config_json.group_days`), `HOLIDAY_CALENDAR` (blocks listed calendar dates via `config_json.holidays`, matched against each slot's materialized `slot_date` from `term_start`), `CONTIGUOUS_LAB_SLOTS` (multi-slot lab sessions: `config_json.block_lengths`/`default_block_length` expands a governed lab subject's `weekly_hours` into contiguous blocks; the checker's double-book/load/reservation checks and the OR-Tools model are block-aware).
  - Pending (separate catalog member): `EXAM_DATE_SEPARATION`.
- [x] **Soft Constraint Scoring** — `app/engine/scorer.py` registry weights each instance's soft constraints into `instance.soft_score` / `generation.score_best_instance` (gated by `enable_soft_constraint_scoring`). Ships `TEACHER_PREFERS_MORNING`, `MINIMIZE_STUDENT_FREE_SLOTS`.
- [x] **OR-Tools CP-SAT Solver** — `app/engine/solvers/or_tools_solver.py`, selectable via `algorithm="OR_TOOLS"`. Domain-prunes with the shared `ConstraintChecker` and adds relational CP-SAT constraints; greedy remains the default preview solver.
- [x] **Soft objective in CP-SAT** — `app/engine/soft_objective.py` (`SOFT_OBJECTIVE_REGISTRY`) folds active soft rules into the OR-Tools objective as weighted linear terms; placements stay strictly primary via `PLACEMENT_WEIGHT=1000.0`. Ships builders for `TEACHER_PREFERS_MORNING` and `MINIMIZE_STUDENT_FREE_SLOTS`; unscored rules still rank instances post-hoc.
- [x] **Diversity Filter** — instance #1 is a deterministic baseline; later instances are re-seeded (greedy shuffles search order, OR-Tools varies `random_seed`) and accepted only if their Hamming distance from earlier instances clears a threshold (retries otherwise). Fixes the "3 identical instances" problem.

### 🟡 Exports, Notifications & Polish
- [x] **Filtered Exports** — PDF/CSV/iCal accept `group_id` / `faculty_id` / `year` / `department` via a shared `get_filtered_slots` helper (`/export/instances/{id}/{pdf,csv,ical}`).
- [x] **iCal (.ics) Export** — weekly-recurring `VEVENT`s (RFC 5545, `RRULE FREQ=WEEKLY`) anchored to `term_start`, optional `term_end`; a teacher imports their schedule with `?faculty_id=`.
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
