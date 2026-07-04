# Progress Tracker — Timetable Generator

This document provides a living status of every feature, table, and improvement discussed in the architecture blueprint (`documentation/timetable-generator-architecture.md`) and the session notes (`rough_plan.md`). 

**Current State:** `v0.greedy-complete` (Foundation + Greedy Engine phase fully implemented).

---

## ✅ Completed Features

### Database & Models
- [x] **18 Database Tables**: Migrated via Alembic (rooms, blackouts, faculty, availability, groups, subjects, profiles, parameters, constraints, generation runs, instances, slots, history, admin, etc.)
- [x] **SQLAlchemy 2.0 ORM**: Declarative models with `mapped_column` and relationship mappings.

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

### Scheduling Engine
- [x] **Greedy Solver**: Priority-based assignment with fast execution for previews.
- [x] **Hard Constraint Checker**: Validates room capacity, faculty availability, blackouts, and basic double-booking prevention before committing slots.
- [x] **Same Subject/Day Rule**: Prevents duplicate subjects on the same day for a group.

### Generation Workflow & Instances
- [x] **Generation Trigger**: `POST /generate` accepts profile/combination, runs solver synchronously.
- [x] **Instance Management**: View generated instances, select a candidate, publish to live system.
- [x] **Manual Slot Override**: Edit individual slots post-generation with backend re-validation.

### Exports & History
- [x] **PDF Export**: Full timetable grid generation using ReportLab.
- [x] **CSV Export**: Data portability for all generated slots.
- [x] **History & Reset**: Archive published timetables, view past snapshots, annual reset workflow (non-destructive).

### API Utilities
- [x] **Query Param Filtering**: Applied across all primary GET routes.

---

## ⏳ Planned / Pending Features

### 🔴 Critical Missing (Blockers for Real Usage)
- [ ] **Subject-Faculty-Group Mapping Table**
  - Who teaches what to which division.
  - Support for cross-department subjects and shared teaching loads (e.g., 80/20 splits).
- [ ] **Cross-Timetable Contamination Fix**
  - Solver must load all currently `PUBLISHED` slots before starting a new run to prevent double-booking across separate generation tasks.
- [ ] **College Settings / Feature Flags Table**
  - ON/OFF toggles per feature so colleges can enable/disable functionality (lab batches, cross-dept, etc.).

### 🟠 Engine & Solver Improvements
- [ ] **Dynamic Constraint Checker**
  - Refactor hardcoded `if/else` checks into a registry that reads `config_json` dynamically.
- [ ] **New Constraint Types**
  - `TEACHER_YEAR_RESTRICTION`, `SUBJECT_TIME_PREFERENCE`, `LAB_BATCH_ROTATION`, `MAX_CONSECUTIVE_SAME_TEACHER`, `CROSS_DEPARTMENT_SUBJECT`, `TEACHING_SHARE`, `HOLIDAY_CALENDAR`, `DIVISION_START_TIME`.
- [ ] **OR-Tools CP-SAT Solver**
  - High-quality primary solver to replace/augment greedy for large departments.
- [ ] **Soft Constraint Scoring**
  - Proper weighted objective function instead of simple slot counting.
- [ ] **Diversity Filter**
  - Ensure generated instances are meaningfully different (Hamming distance check).

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

### 🟢 Frontend Development (Next.js / React)
- [ ] **Auth & Dashboard**: Login, stats view, quick actions.
- [ ] **Resource Management Pages**: Tables, CSV uploads, CRUD modals.
- [ ] **Master Assignment Grid**: UI to map teachers → subjects → divisions.
- [ ] **Profile & Constraint Builder**: Visual form for profiles and dynamic constraints.
- [ ] **Generation Viewer**: Side-by-side instance comparison grid, progress bar for async runs.
- [ ] **Instance Editor**: Click-to-edit slots with live conflict re-checking.

### 🔵 Deployment & Final Polish
- [ ] **Dockerization**: `Dockerfile` + `docker-compose.yml` (App, MySQL, Redis).
- [ ] **README & Docs**: Setup guide, architecture diagram link, API examples.
- [ ] **Historical Data Import**: Upload past semesters' timetables for pattern reference.
- [ ] **ML Preference Learning (Phase 2)**: Learn from manual overrides to suggest constraints automatically.

---

> **How to use this file:** Check off items (`- [x]`) as they are merged into `main`. Use the color coding to prioritize your next sprint (🔴 Critical → 🟠 Engine → 🟡 Polish).
