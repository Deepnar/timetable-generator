# Implementation Plan — Timetable Generator

This plan bridges the gap between our current **Greedy Engine** checkpoint (`v0.greedy-complete`) and the full enterprise vision outlined in `documentation/timetable-generator-architecture.md`. It prioritizes the most critical missing pieces (like subject-faculty mapping and cross-timetable safety) before moving to advanced solvers and frontend development.

---

## Phase 1: Core Engine & Data Mapping Completion
*Goal: Make the current generator actually usable for real college data.*

- [ ] **Subject-Faculty-Group Mapping Table**
  - Design `subject_assignments` table (subject_id, faculty_id, group_id, split_ratio).
  - Handle cross-department subjects (Maths teaching CS + IT) and shared teaching loads (80/20 splits).
  - Update greedy solver to load assignment matrix instead of assuming all teachers teach all subjects.
- [ ] **Cross-Timetable Contamination Fix**
  - Add `load_published_conflicts()` to the scheduler. Before a new generation run, fetch all slots from instances with status `PUBLISHED`.
  - Mark those time-room-teacher-group combinations as pre-blocked for the current solver instance.
- [ ] **College Settings / Feature Flags Table**
  - Create `college_settings` table with boolean toggles per feature (e.g., `enable_lab_batches`, `allow_cross_dept_subjects`).
  - Wrap new optional logic behind these flags so colleges can upgrade incrementally.

## Phase 2: Constraint Engine Overhaul & New Rules
*Goal: Move from hardcoded checks to a dynamic, data-driven constraint system.*

- [ ] **Dynamic Constraint Checker**
  - Refactor `app/engine/constraint_checker.py` to read `config_json` from the constraint model dynamically.
  - Create a registry pattern: `CONSTRAINT_REGISTRY[constraint_type] = validator_function`.
  - Allow new constraint types to be added without modifying core solver code.
- [ ] **Implement New Constraint Types**
  - `TEACHER_YEAR_RESTRICTION`: Prevent assigning teachers outside their allowed years.
  - `SUBJECT_TIME_PREFERENCE`: Hard/soft rules for morning/afternoon slots (e.g., Maths always AM).
  - `LAB_BATCH_ROTATION`: Enforce A1 on Monday, A2 on Tuesday patterns.
  - `MAX_CONSECUTIVE_SAME_TEACHER`: Limit back-to-back slots for a single faculty member.
  - `HOLIDAY_CALENDAR`: Global blackout dates that override all availability.

## Phase 3: Advanced Solvers & Async Infrastructure
*Goal: Handle large departments without blocking HTTP requests.*

- [ ] **Infrastructure Setup**
  - Install and configure **Redis** for caching frequent GET queries, rate limiting, and generation conflict locking.
  - Set up **Celery + Redis** task queue for background processing.
- [ ] **OR-Tools CP-SAT Solver**
  - Integrate `ortools` into `app/engine/solvers/`.
  - Implement proper soft constraint scoring (weighted objective function instead of simple slot counting).
  - Add a **Diversity Filter**: After generating N instances, calculate Hamming distance between them. If two are too similar, discard and regenerate one.
- [ ] **Async Generation Pipeline**
  - Move `POST /generate` to fire a Celery task and immediately return `{status: "PENDING", run_id: X}`.
  - Implement `GET /generate/{run_id}/status` for polling (future: WebSocket upgrades).

## Phase 4: Export, Notifications & Enterprise Polish
*Goal: Production-grade APIs and stakeholder communication.*

- [ ] **Filtered Exports**
  - Update PDF/CSV exports to accept filters: `?group_id=CS-A`, `?faculty_id=5`, or `?year=2`.
  - Implement **iCal (.ics)** export for individual faculty calendar integration.
- [ ] **Notification Service**
  - Set up FastAPI-mail (SMTP).
  - Trigger emails on `POST /instances/{id}/publish`: send individual PDFs to teachers, summary to HODs.
- [ ] **API Polish**
  - Global error handling middleware and consistent JSON error responses.
  - Pagination (`?page=1&limit=20`) on all list endpoints.
  - Request logging / audit trail for every mutation.
  - `GET /health` endpoint for deployment monitoring.

## Phase 5: Frontend Development (React/Next.js)
*Goal: Intuitive UI for college admins who are not technical.*

- [ ] **Auth & Dashboard**
  - Login page, JWT storage, protected routes.
  - Dashboard showing recent generation runs, system stats, and quick actions.
- [ ] **Resource Management Pages**
  - Tables with search/filter, CSV upload modals, and CRUD forms for Rooms, Faculty, Groups, Subjects.
  - **Master Assignment Grid**: UI to assign teachers to subjects and divisions (Phase 1's critical missing piece).
- [ ] **Profile & Constraint UI**
  - Form to build profiles, set parameters, and toggle feature flags.
  - Visual constraint builder (dropdowns for type, weight, and config JSON).
- [ ] **Generation & Instance Viewer**
  - Trigger generation form with progress bar.
  - Side-by-side timetable grid viewer to compare instances.
  - Manual override interface (click slot -> change time/room -> re-validate).

## Phase 6: Deployment & Final Polish
*Goal: Ship a stable, self-contained application.*

- [ ] **Dockerization**
  - `Dockerfile` for FastAPI app, Redis container config, and `docker-compose.yml` for local/env parity.
- [ ] **README & Documentation**
  - Update `README.md` with setup instructions, architecture diagram link, and API examples.
  - Final code cleanup, type hinting pass, and docstrings.

---

> **Note:** All frontend work assumes a separate Next.js repository or an `/frontend` directory. Backend APIs will be versioned at `/api/v1/` during Phase 4 to prevent breaking changes once the frontend is live.
