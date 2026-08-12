# Progress Tracker — Timetable Generator

This document provides a living status of every feature, table, and improvement discussed in the architecture blueprint (`documentation/timetable-generator-architecture.md`) and the session notes (`rough_plan.md`). 

**Current State:** greedy and OR-Tools (CP-SAT) solvers working, data-driven constraint registry, soft-constraint scoring, objective-based instance variation (best / minimize gaps), opt-in async generation (Celery/Redis), a Next.js admin frontend (Auth + Dashboard + Resource CRUD), full-stack Dockerization, and a real-scale seeded college (12 departments, 576 subjects, 345 faculty, 192 groups, 204 rooms, 1152 assignments) that battle-tests the engine — greedy places a whole department's 288 sessions in ~4.3s and all exports hold up.
**Project Scope:** This is a **standalone full-stack enterprise application**, not a microservice. It includes the backend API, PostgreSQL database via Docker, and a Next.js frontend interface for college admins.

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

- **DD-029 — full-project security audit remediated** (v4-pro subagent deepscan, then fixed +
  regression-tested, 209 total). The critical find: the global auth gate authenticated but never
  authorized (only 4 endpoints used `require_roles`), so any teacher/student could do admin
  actions, and public self-registration granted admin. Fixed: router-level role gates (admin+hod,
  or admin-only for constraints/settings/reset/audit), self-registration hardcoded to student,
  sanitized `/health`/generation errors, 8-128 char passwords, CSV upload caps, security headers,
  docs hidden in production, `/generate` rate limit, JWT-expiry check in the frontend. Accepted
  items (httpOnly-cookie JWT, psycopg2-binary, Next/React patch bumps) tracked as follow-ups.

- **DD-024 — real-college scheduling rules are only partially modeled** (flagged by the founder;
  see `design-decisions.md`). Batches (2 batches 2nd–4th yr, 3 in 1st yr; parallel 2h practicals
  per batch) have a `BATCH` group_type but no seed/solver support; "max one practical subject per
  day" is unenforced; subjects have no explicit tutorial/practical/`both` attribute driving two
  session streams; the time grid is one shared slot list, not per-day; and cross-timetable
  conflict reservations only cover PUBLISHED instances, not all active (DRAFT/SELECTED) ones.
  Verify each against real data, then design (see DD-024 next steps).
- **DD-025 — single-college posture decided.** The product ships for one college; everything
  college-specific is data (settings/groups/params), never hardcoded engine logic. Class strength
  and batch division are teacher-set with system suggestions. A founder detail log captures
  remembered real-world details until they become DD entries. Generalize to multi-tenant only
  when a second college asks.

- ~~**Room blackout check is effectively dead**~~ — ✅ FIXED: `room_blackouts` now supports recurring **weekday** blackouts (`day_of_week`), which the checker enforces against the recurring templates. Date-specific blackouts still await calendar-date materialization.
- ~~**Faculty availability date-range ignored**~~ — ✅ FIXED: `effective_from`/`effective_to` are now nullable (migration `e9f4a2b6d8c0`) so timeless windows can be created via CRUD/CSV, and the checker consults them against each slot's materialized date. The solver anchors the weekly template with the new **`term_start`** profile parameter (see architecture §8.8) and stamps `TimetableSlot.slot_date`; a date-bounded window only blocks the week it covers, and a window with no bounds stays timeless.
- ~~**CSV import is not atomic**~~ — ✅ FIXED: `/import/{rooms,faculty,groups,subjects}` are now **all-or-nothing**. Every row is validated up front (required fields, duplicates within the file AND against the DB); any invalid row rejects the whole upload with `422` and `inserted=0`, so the DB never ends up holding rows the response didn't report. `import_rooms` also now requires a non-empty `room_code`.
- ~~**Profile combinations are never resolved**~~ — ✅ FIXED: `ProfileResolver` (`app/engine/profile_resolver.py`) merges combination members into an effective profile before solving — resources unioned (de-dup by `(resource_type, resource_id)`), parameters resolved with the **highest-weight member winning collisions**, hard/soft constraints merged from every member plus globals. `POST /generate` with `combination_id` now schedules all members' resources; the generation row stores `combination_id` with `profile_id=NULL`. `POST /profiles/combine` validates member existence and weights length; slot-override re-validation re-resolves the combination too. See architecture §6.2.
- ~~**`GET /constraints/types` is a hardcoded string list**~~ — ✅ FIXED: the endpoint now derives its hard/soft lists from `HARD_CONSTRAINT_TYPES` / `SOFT_CONSTRAINT_TYPES` (defined next to the `ConstraintType` enum), so discovery can never drift from what the Create schemas accept.
- ~~**Read-route auth is inconsistent**~~ — ✅ FIXED: every route now requires a valid admin JWT except `GET /health` and the `/auth/*` endpoints (`register`/`login`). Enforced by one global middleware (`require_auth` in `app/main.py`) instead of a per-route dependency, so a new router/endpoint cannot accidentally be left public; `/docs` and `/openapi.json` are gated too. `get_current_admin` remains only on mutations that need the admin identity. See architecture §4.2 / §7.4.

---

## ✅ Completed Features

### Database & Models
- [x] **22 Database Tables**: Migrated via Alembic (admins, audit_logs, rooms, blackouts, faculty, availability, groups, subjects, subject_assignments, college_settings, profiles, parameters, combinations, hard/soft constraints, generation runs, instances, slots, history, reset log, etc.)
- [x] **SQLAlchemy 2.0 ORM**: Declarative models with `mapped_column` and relationship mappings.
- [x] **Database Migration to PostgreSQL**: Switched from local MySQL to Docker-managed Postgres 15 container.

### Authentication & Security
- [x] **JWT Auth**: Admin login, token refresh, bcrypt password hashing.
- [x] **Global Auth Gate**: every route requires a valid admin JWT via a single `require_auth` middleware — exempt only `GET /health` and `/auth/*`. Replaced the old "mutations only" posture where all reads were public.
- [x] **RBAC**: `Admin.role` (`admin`/`hod`/`teacher`/`student`, default `admin`), JWT role claim, `require_roles(...)` dependency, `GET /auth/me`, admin-only `POST /auth/users` (DD-021). Teacher/student read-scoping is a documented follow-up.
- [x] **CORS Middleware**: Configured for frontend communication (localhost:3000).

### Resource Management (CRUD)
- [x] **Rooms API**: Full CRUD, blackout window management, query param filtering (type, building, capacity). Rooms carry `equipment_json` (free-form feature tags) and accept the `CUSTOM` room type.
- [x] **Faculty API**: Full CRUD, availability windows, filtering.
- [x] **Student Groups API**: Full CRUD, hierarchical grouping support, filtering.
- [x] **Subjects API**: Full CRUD, subject-hours mapping, filtering. Subjects carry `requirements_json` (room_types / min_capacity / features / session_type) which replaces `requires_lab`.
- [x] **CSV Bulk Import**: Robust parser for all 4 entities with validation. All-or-nothing (any bad row rejects the file with `422`, `inserted=0`). Rooms/subjects CSV accepts the new JSON columns.

### Profiles & Constraints
- [x] **Profile System**: Create/edit profiles, link resources, set parameters.
- [x] **Profile Combinations**: Merge multiple profiles into an effective profile (`app/engine/profile_resolver.py`); resolution happens automatically at generation time — resources unioned, parameters weighted (highest weight wins on collisions), hard/soft constraints merged from every member plus globals (§6.2). Discoverable/previewable via `GET /profiles/combinations` (members, weights, `resolution_status`) and `POST /profiles/combinations/{id}/resolve` (merged `ResolvedProfile` preview; runs the same resolver the scheduler uses).
- [x] **Constraint CRUD**: Hard and soft constraint tables, weight management, profile scoping.

### Scheduling Engine & Data Mapping (Phase 1)
- [x] **Greedy Solver**: Priority-based assignment with fast execution for previews.
- [x] **Hard Constraint Checker**: Validates room capacity, faculty availability, blackouts, and basic double-booking prevention before committing slots.
- [x] **Subject-Faculty-Group Mapping Table**: `subject_assignments` table created to handle exact mappings, cross-dept subjects, and shared teaching loads (80/20 splits). Greedy solver now reads from this table instead of guessing.
- [x] **Cross-Timetable Contamination Fix**: Scheduler now fetches all `PUBLISHED` slots before running a new generation, preventing double-bookings across separate timetable runs.

### Generation Workflow & Instances
- [x] **Generation Workflow & Instances**
  - [x] **Generation Trigger**: `POST /generate` accepts profile/combination, runs solver synchronously (default) or asynchronously via Celery/Redis when `ASYNC_GENERATION=true` (returns 202 PENDING; see "Async Generation" below).
  - [x] **Placement visibility**: a run that completes but cannot place every session stamps `placement_warning` (e.g. "N session(s) could not be placed") on the generation row and API response, so oversubscribed profiles are visible instead of silent COMPLETED.
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
  - ✅ `enable_lab_batches` now gates the `LAB_BATCH_ROTATION` registry rule (inert by default, opt-in per college). `enable_soft_constraint_scoring` gates soft scoring in both solvers (see §3.3).

### 🟠 Engine & Solver Improvements
- [x] **Dynamic Constraint Checker** *(foundation)* — `app/engine/constraint_registry.py` dispatches profile `hard_constraints` (by `config_json`) to registered validators; `constraint_type` is now a plain string so new rules skip schema migrations. Core structural checks now live in the registry too as always-on `STRUCTURAL_RULES` (`ConstraintChecker.check_all` dispatches them on every candidate, independent of profile rows) — see plan.md Phase 2.
- [x] **Generic room requirements** — `Subject.requirements_json` (room_types / min_capacity / features / session_type) matched against `Room.equipment_json` + legacy boolean columns by `app/engine/resource_requirements.py`. `requires_lab` is now shorthand for `{"room_types": ["LAB"]}`; the registry rule `ROOM_TYPE_MATCH` became `ROOM_REQUIREMENTS_MET`; both solvers pick rooms through the shared matcher. See architecture §5.5.
- [x] **CUSTOM escape hatches** — `CUSTOM` added to `RoomType` and `SessionType` (migration `d7a3c5e9f1b2`); free-form attributes hang off `equipment_json`/`requirements_json`. `GroupType` already had `CUSTOM`.
- [x] **New Constraint Types** *(8 of 8 done)*
  - Done: `SUBJECT_TIME_PREFERENCE`, `MAX_CONSECUTIVE_SAME_TEACHER`, `MAX_DAILY_SUBJECTS` (caps distinct subjects per group per day via `config_json.max`; relational in OR-Tools), `TEACHER_YEAR_RESTRICTION`, `LAB_BATCH_ROTATION` (pins a group/lab-batch to weekdays via `config_json.group_days`), `HOLIDAY_CALENDAR` (blocks listed calendar dates via `config_json.holidays`, matched against each slot's materialized `slot_date` from `term_start`), `CONTIGUOUS_LAB_SLOTS` (multi-slot lab sessions: `config_json.block_lengths`/`default_block_length` expands a governed lab subject's `weekly_hours` into contiguous blocks; the checker's double-book/load/reservation checks and the OR-Tools model are block-aware), `EXAM_DATE_SEPARATION` (min days between a group's exams: a `session_type: EXAM` profile mode turns each assignment into one `SessionType.EXAM` session; the validator spaces exams by `slot_date`, OR-Tools models it as a relational rule, and the published-conflict loader exempts the examing groups' own class slots so one branch can sit exams while others teach — architecture §5.4).
- [x] **Soft Constraint Scoring** — `app/engine/scorer.py` registry weights each instance's soft constraints into `instance.soft_score` / `generation.score_best_instance` (gated by `enable_soft_constraint_scoring`). Ships scorers + CP-SAT builders for all six catalogued types (`TEACHER_PREFERS_MORNING`, `AVOID_CONSECUTIVE_SAME_SUBJECT`, `MINIMIZE_STUDENT_FREE_SLOTS`, `MINIMIZE_TEACHER_FREE_SLOTS`, `DISTRIBUTE_SUBJECTS_EVENLY`, `BALANCE_TEACHER_LOAD`); the greedy solver now also pursues them during placement (preference-aware scan).
- [x] **OR-Tools CP-SAT Solver** — `app/engine/solvers/or_tools_solver.py`, selectable via `algorithm="OR_TOOLS"`. Domain-prunes with the shared `ConstraintChecker` and adds relational CP-SAT constraints; greedy remains the default preview solver.
- [x] **Soft objective in CP-SAT** — `app/engine/soft_objective.py` (`SOFT_OBJECTIVE_REGISTRY`) folds active soft rules into the OR-Tools objective as weighted linear terms; placements stay strictly primary via `PLACEMENT_WEIGHT=1000.0`. Ships builders for `TEACHER_PREFERS_MORNING` and `MINIMIZE_STUDENT_FREE_SLOTS`; unscored rules still rank instances post-hoc.
- [x] **Diversity Filter + objective-based variation** — instance #1 is a deterministic baseline; later instances are re-seeded (greedy shuffles search order, OR-Tools varies `random_seed`) and accepted only if their Hamming distance from earlier instances clears a threshold (retries otherwise). Fixes the "3 identical instances" problem. `POST /generate` now also accepts `variation` (`random` / `best` / `minimize-teacher-gaps` / `minimize-student-gaps`): `"best"` seeds instance #1 and keeps the highest-scoring distinct attempt; the gap modes reshape the seeded re-rolls (greedy reorders its search around the peer's placements via `_criterion_scan`, OR-Tools adds a span term to the CP-SAT objective). See architecture §5.3. The Hamming threshold is now a `diversity_threshold` profile parameter.
- [x] **Placement visibility** — a run that completes but drops sessions stamps `placement_warning`; instances carry an honestly-computed `hard_violations` (re-validated with the full checker).
- [x] **Wired profile params** — `solver_timeout_seconds` (OR-Tools budget) and `diversity_threshold` are read from `profile_parameters`; `ALLOW_FREE_LAST_SLOT` (keep the last slot free) is a new data-driven hard rule alongside `MAX_DAILY_SUBJECTS`.
- [x] **Scope-driven exam mode** — `scope_type=EXAM` implies exam mode (the `session_type` parameter is no longer required); the resolver surfaces the effective scope to the solvers.

### 🟡 Exports, Notifications & Polish
- [x] **Filtered Exports** — PDF/CSV/iCal accept `group_id` / `faculty_id` / `year` / `department` via a shared `get_filtered_slots` helper (`/export/instances/{id}/{pdf,csv,ical}`).
- [x] **iCal (.ics) Export** — weekly-recurring `VEVENT`s (RFC 5545, `RRULE FREQ=WEEKLY`) anchored to `term_start`, optional `term_end`; a teacher imports their schedule with `?faculty_id=`.
- [x] **Email Notifications on Publish**
  - Opt-in SMTP mailer (`app/services/mail_service.py`, `.env` `EMAIL_ENABLED` + `SMTP_*`): on `POST /instances/{id}/publish` each faculty gets their personal PDF, HOD/admin addresses (`CollegeSettings.config_json["notification_emails"]`) the full-instance summary, and class incharges (`student_groups.incharge_email`, migration `f5a1b3c8e6d2`) their group's PDF. Delivery runs in a non-blocking daemon thread; unconfigured SMTP is a strict no-op and a mail failure never fails the publish. Tested against a mocked delivery layer (`app/tests/test_email_notifications.py`). See architecture §7.7 / §8.9.
- [x] **Redis Integration**
  - Optional client (`app/services/redis_client.py`, `REDIS_ENABLED` + `REDIS_URL`) with graceful degradation: **generation-conflict locking** (`Scheduler.solve_generation` locks the run's resource set; a busy lock marks the run FAILED and `POST /generate` returns 409), **response caching** for `GET /rooms/` `/subjects/` `/profiles/` `/settings/` (60s TTL, busted on matching writes), and **IP rate limiting** on `/auth/login` (5/min) + `/auth/register` (3/min) → 429. All inert when Redis is down or disabled; the SQLite suite forces `REDIS_ENABLED=false` and tests against a fake client (`app/tests/test_redis_integration.py`). See architecture §7.9.
- [x] **Async Generation (Celery)**
  - Move long-running solver tasks out of the HTTP request cycle. `ASYNC_GENERATION=true` makes `POST /generate` return **202 PENDING** (with `run_id`) and enqueue `app/tasks/generation.py::run_generation`; the worker (`app/worker.py`) runs `Scheduler.solve_generation()`, which flips the run to COMPLETED (or FAILED with `error_log`) and stamps `run_duration_ms`. `GET /generate/{run_id}/status` polls PENDING/RUNNING/COMPLETED/FAILED. Default remains synchronous (`ASYNC_GENERATION=false`) so the SQLite test suite needs no Redis. See architecture §7.1.
- [x] **API Polish**
  - Pagination (`skip/limit`) on every top-level list endpoint with `X-Total-Count`; global `{"detail": ...}` error envelope with `request_id` on 422/500; request logging/audit trail; `GET /health`; API versioning — `/api/v1/` aggregator keeps unversioned paths live (`app/main.py`, §7.10). Tested in `app/tests/test_api_polish.py`.

### 🟢 Full Stack Frontend Development (Next.js / React)
*This is now a core part of this project, not an external consumer.*
- [x] **Frontend Initialization**: Setup Next.js app within the full-stack deployment pipeline. — `frontend/` (Next.js 14 App Router + TypeScript + Tailwind), `src/lib/api.ts` fetch client (JWT Bearer + `X-Total-Count`), `AuthProvider`, `ProtectedShell` guard (DD-017).
- [x] **Editorial-light restyle**: the admin UI is themed with warm canvas, white shadow-separated cards, serif display headings, uppercase tracked labels, and charcoal accents (`tailwind.config.ts`, `globals.css`, all components/pages). A raw-CDP screenshot harness (`frontend/scripts/screenshot.mjs`) performs a real login and captures every page for visual verification via the vision skill; it surfaced and fixed the auth-init race and a title-singularization bug.
- [x] **Auth & Dashboard**: Login page (`/auth/login` → JWT in localStorage), protected routes, stats view (resource counts), quick actions.
- [x] **Resource Management Pages**: CRUD tables with server pagination + filters and **drill-down navigation** (category tiles, facet rail, breadcrumbs, URL state) for Rooms, Faculty, Groups, Subjects (driven by the shared `ResourcePage`; adds `PUT /groups/{id}` for full CRUD parity). Drill-down probes surfaced and fixed the CORS `X-Total-Count` exposure bug.
- [x] **Generation & Instance Viewer (read path)**: `/generate` (profile picker, solver radio, instance count, run cards with 2s status polling — `placement_warning`/`error_log` surfaced), `/instances` (all-instances list via the new `GET /instances/` endpoint, status badges, scores), `/instances/[id]` (the **TimetableGrid**: pure-CSS day×slot grid with sticky headers, subject-hued color coding, row-spanning lab blocks, faculty/room/group per cell, PDF/CSV/iCal/Select/Publish actions), and `/exports` hub.
- [x] **Compare mode**: `/instances/compare?a=&b=` — two scroll-synced TimetableGrids with per-cell add/remove/change markers, a summary bar (score/violation/moved deltas), and a click-to-scroll diff list. The diff is computed client-side from the two `/slots` lists (no backend compare endpoint needed). Entry points from the instances list and the instance viewer.
- [x] **Slot override UI**: click a DRAFT/SELECTED cell → anchored editor (day/slot/room/faculty selects + reason). A debounced `POST /instances/{id}/slots/{slotId}/revalidate` dry-run reports conflicts before saving; Save stays disabled until clean. Backend revalidate endpoint wraps `_check_candidate` (shared with the PATCH) and returns `{"slot_id", "violations"}` with 200 even on conflicts; a slot move re-derives start/end from the profile's time grid.
- [x] **Mid-year change loop** (DD-026): `timetable_overrides` table + endpoints (list/create/swap/resolve/available-faculty) let admins record in-term changes to a **published** timetable without touching its base slots — teacher covers, room changes, lecture swaps, and temporary (date-window) changes. Changes are conflict-checked against the instance's other slots + published reservations (409 on conflict); reverted changes stay as history. **Change mode** on the published instance viewer: click a cell → Apply-change editor with a covering-teacher dropdown fed by `available-faculty` (only teachers free at that day/slot), plus a Mid-year changes panel with a Revert action.
- [x] **Teacher portal (DD-022 #1)**: `/my-schedule` — role-based login redirects teachers to it; a **Today card** (their sessions for the current weekday from `GET /my/today`), a read-only weekly TimetableGrid fed by `GET /my/schedule` (own published slots with names resolved), and one-click iCal/PDF via `GET /my/export/{pdf,csv,ical}` (own filtered export from the newest published instance). The teacher's Faculty row is resolved by email match; an empty state appears when unmatched or nothing is published. The seed provisions a demo teacher login linked to a real Faculty row.
- [x] **Student portal (DD-022 #1)**: `/my-timetable` — role-based login redirects students to it; a **Today card** (their group's sessions from `GET /my/today`), the group's published timetable as a read-only grid (cells show the faculty name), and own iCal/PDF via `GET /my/export`. The group is found via a new `student_groups.student_email` column (migration `9fe4f7187298`); the seed links the demo student login to a group. Empty states for unlinked/unpublished.
- [x] **Two-channel notifications (DD-027)**: on publish and on mid-year changes, the relevant people are notified in-app (new `app_notifications` table — one row per recipient Admin, resolved by email from the schema links) plus email (existing publish mailer + a compact change email). `notification_service.dispatch_publish` / `dispatch_change` run after the commits, best-effort. The topbar **bell** shows the caller's unread count and a dropdown; `/notifications` lists/marks rows (`GET /notifications`, `unread-count`, `{id}/read`, `read-all`). Also fixed a real bug: override validation no longer conflicts with the instance being changed itself (`Scheduler._load_published_conflicts(exclude_instance_id=...)`).
- [x] **Date-resolution day layer (DD-022 #2 / DD-026 follow-up)**: `app/services/override_resolver.py` resolves `timetable_overrides` against a real date — a permanent cover/room change applies every date, a TEMP window wins inside its `date_from`/`date_to`, a SWAP exchanges the two slots' faculty/room, and a covered slot reports the new teacher/room. `/my/schedule` + `/my/timetable` accept `?date=YYYY-MM-DD` and `/my/today` resolves against today, so "is there class on date X" and the day card are truthful. The teacher/student Today cards gained a date picker.
- [x] **Full-college timetable (founder's final seed goal)**: `scripts/generate_college.py` generates + publishes a timetable for the ENTIRE college — one whole-department instance per department (best-wins variation), all semesters/divisions at once. Ran clean: 12/12 departments published, 3456 slots. (`--only`, `--dry-run`, `--clear-locks` options.)
- [x] **Security audit (DD-029)**: see "Newly Identified" — role gates, least-privilege registration, hardened error/upload/header surfaces, `/generate` rate limit, JWT-expiry check. 209 tests.
- [ ] **CSV upload modals** (part of Resource Management).
- [x] **Assignment grid**: `/assignments` — a subject × group matrix scoped by department + semester (rows = subjects, columns = division groups), with faculty avatar + weekly-hours badge per cell, an anchored cell editor (assign/change faculty + hours, remove), per-subject coverage chips, and a least-loaded-faculty **Auto-fill unassigned** bulk action. Drives the same `subject_assignments` CRUD the solver reads.
- [x] **Profile & Constraint Builder**: `/profiles` (card grid of presets with create drawer + archive) and `/profiles/[id]` (four tabs: **Resources** per-type shuttles, **Parameters** catalog-driven key/value rows with JSON validation, **Constraints** hard + soft rows from the `GET /constraints/types` catalog with inline soft-weight editing, **Runs** generation history). The Generate button preselects the profile via `?profile=N`.
- [ ] **Instance Editor**: Click-to-edit slots with live conflict re-checking. *(Core done — see "Slot override UI"; polish left.)*

### 🔵 Deployment & Final Polish
- [x] **Full Stack Dockerization**: top-level `docker-compose.yml` (App, Frontend, PostgreSQL, Redis) + backend `Dockerfile` (uv, migrates on boot) + `frontend/Dockerfile` (standalone Next). `docker/docker-compose.yml` remains the backend-only dev infra (DD-018). *(`docker compose up` four-service bring-up pending on a free host port 3000 — see DD-018 follow-up.)*
- [x] **Scale battle test**: `scripts/seed_demo.py` seeds a 12-department college modeled on the `sample/` TCET timetables (576 subjects, 345 faculty, 192 groups, 204 rooms, 1152 assignments, 108 profiles). `scripts/battle_test.py`, `scripts/api_drive.py`, `scripts/async_drive.py` run real generations (greedy + OR-Tools, sync + async Celery, generation lock, publish → cross-timetable safety) against live Postgres/Redis. Surfaced and fixed two real bugs: unfiltered multi-group PDF export (ReportLab `LayoutError`) now renders one grid per group, and `GenerationResponse` now reports `run_duration_ms`. See DD-020.
- [x] **Full-features-at-scale verification**: `scripts/full_stack_test.py` re-verifies every capability at whole-department scale (soft pursuit, `MAX_DAILY_SUBJECTS`/`ALLOW_FREE_LAST_SLOT`, OR-Tools relational rules + greedy fallback, honest `hard_violations`/`placement_warning`, RBAC, conflict audit, real Celery async path). Surfaced and fixed: OR-Tools returning 0 slots on a big relational-rule profile (now greedy-fallback), and duplicate admin names 500ing (now 409).
- [ ] **README & Docs**: Setup guide, architecture diagram link, API examples.
- [ ] **Historical Data Import**: Upload past semesters' timetables for pattern reference.
- [ ] **ML Preference Learning (Phase 2)**: Learn from manual overrides to suggest constraints automatically.

---

> **How to use this file:** Check off items (`- [x]`) as they are merged into `main`. Use the color coding to prioritize your next sprint (🔴 Critical → 🟠 Engine → 🟡 Polish).
