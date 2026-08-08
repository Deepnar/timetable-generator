# Implementation Plan — Timetable Generator

This plan bridges the gap between our current **Greedy Engine** checkpoint (`v0.greedy-complete`) and a **complete, standalone full-stack enterprise application**. It prioritizes the most critical missing pieces (like subject-faculty mapping and cross-timetable safety) before moving to advanced solvers and frontend development.

> **Plan review (cross-check pass):** The phase ordering is sound. Two adjustments worth making:
> (1) **Phase 2 (dynamic constraint registry) is the real flexibility unlock and should land before Phase 3 (OR-Tools)** — a better solver that can only express 9 hardcoded rules is still rigid. (2) The greedy engine and OR-Tools should share **one constraint interface** so rules are written once and both solvers consume them; otherwise every new rule is implemented twice. See the reworked "extreme flexibility" section under Phase 1 for what that goal concretely requires, and `progress.md` → "Newly Identified" for bugs this plan doesn't yet track.

---

## Phase 1: Core Engine & Data Mapping Completion
*Goal: Make the current generator actually usable for real college data.*

- [x] **Subject-Faculty-Group Mapping Table**
  - Design `subject_assignments` table (subject_id, faculty_id, group_id, split_ratio).
  - Handle cross-department subjects (Maths teaching CS + IT) and shared teaching loads (80/20 splits), and not just restricted to one subject.
  - Update greedy solver to load assignment matrix instead of assuming all teachers teach all subjects.
- [x] **Cross-Timetable Contamination Fix**
  - Add `load_published_conflicts()` to the scheduler. Before a new generation run, fetch all slots from instances with status `PUBLISHED`.
  - Mark those time-room-teacher-group combinations as pre-blocked for the current solver instance.
- [x] **College Settings / Feature Flags Table**
  - `college_settings` singleton table created (`enable_lab_batches`, `allow_cross_dept_subjects`, `enable_soft_constraint_scoring`, plus a free-form `config_json`). Auto-created on startup and via `get_settings()`.
  - Exposed at `GET/PUT /settings/`; solver already honors `allow_cross_dept_subjects` and the checker reads `config_json.max_cross_dept_per_day`.
  - *Remaining:* wrap the rest of the optional logic (e.g. `enable_lab_batches`, `enable_soft_constraint_scoring`) behind these flags as those features land.
  - [ ] **Making the system extremely flexible** *(the "any timetable of anything" goal)*
  - The engine is currently hardwired to an Indian-college class timetable (departments, semesters, years, lab-vs-classroom, one-subject-per-day, fixed 9 AM start). "Extreme flexibility" concretely means removing those hardcoded assumptions so the *data* — not the code — decides the shape of a timetable. Four independent levers, in priority order:
    1. **Configurable time grid** *(started)* — day start (`day_start_time` ✅), slot count/duration, breaks are already profile params. Still needed: variable-length slots. **Multi-slot sessions** ✅ done — `CONTIGUOUS_LAB_SLOTS` (Phase 2) runs a governed lab subject's `weekly_hours` as contiguous blocks (a 3-hour lab occupying consecutive slots in one room/teacher/group), wired through both solvers and the checker. `SAME_SUBJECT_SAME_DAY` still forbids a second session of the *same subject* on the same day, which intentionally caps a subject at one block per day.
    2. **Data-driven constraints** — the single biggest lever. The `hard_constraints`/`soft_constraints` tables + `config_json` already exist but the checker ignores them and hardcodes 9 rules. Phase 2's registry is what actually delivers "new rules without code changes." **Do Phase 2 before OR-Tools.**
    3. **Generic resource requirements** — replace `Subject.requires_lab` (a single bool) with declared requirements (capacity, room features like projector/AC, equipment tags) matched against room attributes. Removes the binary lab/not-lab assumption.
    4. **Loosen the closed vocabularies** — `RoomType`/`SessionType`/`GroupType`/`TimetableType` are fixed enums. For non-college use (exam halls, events, shift rosters) these need a `CUSTOM` escape hatch with free-form attributes, or a tag system.
  - **Guiding principle:** every new capability ships behind a `college_settings` flag and defaults OFF, so the "standard college" preset stays simple (ease of use) while power users opt into complexity (flexibility).


## Phase 2: Constraint Engine Overhaul & New Rules
*Goal: Move from hardcoded checks to a dynamic, data-driven constraint system.*

- [x] **Dynamic Constraint Checker** *(foundation done)*
  - `app/engine/constraint_registry.py` maps `constraint_type` → validator; the checker loads a profile's active `hard_constraints` rows (plus global ones) and dispatches each with its `config_json`.
  - `constraint_type` is now a plain string column (migration `b7d9f2a1c3e4`), so new rule types need **no** schema migration.
  - *Remaining:* the core structural checks (double-booking/capacity/availability) are still inline; optionally fold them into the registry as always-on entries so every rule is uniform.
- [x] **Profile Combination Resolution**
  - `POST /profiles/combine` now validates members (existence, weights length). `Scheduler.run()` resolves `combination_id` into an effective profile before solving (`app/engine/profile_resolver.py`): resources unioned (de-dup by type+id), parameters merged with the highest-weight member winning collisions, hard/soft constraints merged from every member plus globals. See architecture §6.2.
  - `GET /profiles/combinations` lists combinations with member profiles/weights and a `resolution_status` preview; `POST /profiles/combinations/{id}/resolve` returns the merged `ResolvedProfile` for manual preview (same `ProfileResolver` the scheduler uses). See architecture §4.2.
- [x] **Implement New Constraint Types** *(7 of 7 done)*
  - [x] `TEACHER_YEAR_RESTRICTION`: Prevent assigning teachers outside their allowed years.
  - [x] `SUBJECT_TIME_PREFERENCE`: Confine a subject to a slot window (e.g., Maths always AM).
  - [x] `MAX_CONSECUTIVE_SAME_TEACHER`: Limit back-to-back slots for a single faculty member.
  - [x] `LAB_BATCH_ROTATION`: Pin a group/lab-batch to specific weekdays (A1 Mon, A2 Tue) — `config_json.group_days`.
  - [x] `HOLIDAY_CALENDAR`: Blackout specific calendar dates via `config_json.holidays` (`["YYYY-MM-DD", ...]`). The validator matches each candidate's materialized `slot_date` (anchored by the profile's `term_start`, §8.8) and is a no-op when the slot has no date. Wired into both solvers through the shared registry.
  - [x] `CONTIGUOUS_LAB_SLOTS`: Multi-slot lab sessions. `config_json.block_lengths` (`{"<subject_id>": int}`) + optional `default_block_length`; a governed lab subject's `weekly_hours` expands into contiguous blocks (remainder stays single-slot). Block-aware checker (double-book/load/reservations) and OR-Tools modeling (per-start-slot variables with per-sub-slot exclusivity); `SUBJECT_TIME_PREFERENCE` and `MAX_CONSECUTIVE_SAME_TEACHER` understand blocks.
  - [x] `EXAM_DATE_SEPARATION`: Minimum days between a group's exams. Driven by a `session_type: EXAM` profile mode (each assignment becomes one `SessionType.EXAM` session) + `config_json.min_days`; the validator spaces exams by their materialized `slot_date`, OR-Tools models it as a relational CP-SAT rule, and the published-conflict loader exempts the examing groups' own class slots so one branch/year can sit exams while the others keep teaching (see architecture §5.4).

## Phase 3: Advanced Solvers & Async Infrastructure
*Goal: Handle large departments without blocking HTTP requests.*

- [x] **Infrastructure Setup**
  - Install and configure **Redis** for caching frequent GET queries, rate limiting, and generation conflict locking.
  - Set up **Celery + Redis** task queue for background processing.
  - `docker/docker-compose.yml` now also runs a `redis:7-alpine` service; the Celery app lives in `app/worker.py` (`uv run celery -A app.worker:celery_app worker`). *Remaining:* using the same Redis for caching/rate-limiting (the task queue itself is wired below).
- [x] **Soft Constraint Scoring** *(done, solver-independent)*
  - `app/engine/scorer.py` registry scores each instance's soft constraints (weighted mean → `instance.soft_score`, best → `generation.score_best_instance`), gated by `enable_soft_constraint_scoring`. Ships `TEACHER_PREFERS_MORNING` and `MINIMIZE_STUDENT_FREE_SLOTS`. This is the objective function OR-Tools reuses.
- [x] **OR-Tools CP-SAT Solver** *(integrated)*
  - `app/engine/solvers/or_tools_solver.py` — select via `algorithm="OR_TOOLS"`. Static rules prune the CP-SAT domain (shared `ConstraintChecker`), relational rules are CP-SAT constraints, objective maximises placements (strictly primary via `PLACEMENT_WEIGHT`) and then optimises the active soft preferences. Greedy stays the default/preview solver.
  - Soft rules with an objective builder in `app/engine/soft_objective.py` (`SOFT_OBJECTIVE_REGISTRY`) are folded into the CP-SAT objective, so OR-Tools *pursues* preferences (gated by `enable_soft_constraint_scoring`); unscored rules still rank instances post-hoc.
- [x] **Diversity Filter**: Instance #1 is a deterministic baseline; later instances are re-seeded (greedy randomises search order, OR-Tools varies `random_seed`) and kept only if their Hamming distance from accepted instances clears a threshold, retrying otherwise. **Objective-based variation implemented** — `POST /generate` accepts `variation` (`random` / `best` / `minimize-teacher-gaps` / `minimize-student-gaps`): `"best"` seeds instance #1 too and keeps the highest-scoring distinct attempt; the gap modes reshape the seeded re-rolls (greedy reorders its search around the peer's placements, OR-Tools adds a span term to the objective).
- [x] **Async Generation Pipeline**
  - `POST /generate` fires a Celery task and immediately returns `{status: "PENDING", run_id}` when `ASYNC_GENERATION=true` (202); otherwise it stays synchronous (201). `Scheduler` splits into `create_generation()` (persists the PENDING row) and `solve_generation()` (worker entry point, flips to COMPLETED/FAILED with `error_log`, stamps `run_duration_ms`). See architecture §7.1.
  - `GET /generate/{run_id}/status` for polling (future: WebSocket upgrades).

## Phase 4: Full Stack Integration & Frontend Development
*Goal: Provide a complete user experience within this single application.*

- [ ] **Frontend Setup**
  - Initialize Next.js/React frontend inside this project (or as a tightly coupled sibling).
  - Set up API client, authentication context, and routing.
- [ ] **Auth & Dashboard**
  - Login page, JWT storage, protected routes.
  - Dashboard showing recent generation runs, system stats, and quick actions.
- [ ] **Resource Management Pages**
  - Tables with search/filter, CSV upload modals, and CRUD forms for Rooms, Faculty, Groups, Subjects.
  - **Master Assignment Grid**: UI to assign teachers to subjects and divisions (Phase 1's critical missing piece).
- [ ] **Generation & Instance Viewer**
  - Trigger generation form with progress bar.
  - Side-by-side timetable grid viewer to compare instances.
  - Manual override interface (click slot -> change time/room -> re-validate).

## Phase 5: Enterprise Polish, Exports & Notifications
*Goal: Production-grade APIs and stakeholder communication.*

- [x] **Filtered Exports**
  - PDF/CSV/iCal all accept `?group_id=`, `?faculty_id=`, `?year=`, `?department=` (shared `get_filtered_slots`).
  - **iCal (.ics)** export implemented — weekly-recurring `VEVENT`s with `?term_start`/`?term_end`, ideal for a teacher importing their personal schedule (`?faculty_id=`).
- [ ] **Notification Service**
  - Set up FastAPI-mail (SMTP).
  - Trigger emails on `POST /instances/{id}/publish`: send individual PDFs to teachers, summary to HODs.
- [ ] **API Polish**
  - Global error handling middleware and consistent JSON error responses.
  - Pagination (`?page=1&limit=20`) on all list endpoints.
  - Request logging / audit trail for every mutation.
  - `GET /health` endpoint for deployment monitoring.
- [x] **Global Auth Gate** — every route (except `/health` + `/auth/*`) requires a valid admin JWT via a single `require_auth` middleware in `app/main.py`, replacing the per-route "mutations only" posture. New routers/endpoints cannot accidentally be left public; OpenAPI docs are gated too. (Phase 1/5 auth hardening, see architecture §4.2.)

## Phase 6: Deployment & Final Polish
*Goal: Ship a stable, self-contained full-stack application.*

- [ ] **Full Stack Dockerization**
  - Create a top-level `docker-compose.yml` that spins up the entire application: **FastAPI Backend**, **Next.js Frontend**, **PostgreSQL Database**, and **Redis** in one command. (The current `docker/docker-compose.yml` only runs Postgres.)
- [ ] **README & Documentation**
  - Update `README.md` with setup instructions, architecture diagram link, and API examples.
  - Final code cleanup, type hinting pass, and docstrings.
- [ ] **Historical Data Import**
  - Upload past semesters' timetables for pattern reference.

---

> **Note:** This application is now a standalone full-stack project. All frontend work will be integrated into the deployment pipeline, making this a single deployable artifact.
