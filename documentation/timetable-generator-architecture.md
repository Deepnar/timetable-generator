# Timetable Generator — Architecture Blueprint
> Standalone FastAPI + PostgreSQL application | Status: greedy + OR-Tools solvers working, data-driven constraint registry, soft-constraint scoring

This document is the architectural blueprint for the Timetable Generator backend. The service is a **standalone product** — it is not a module of a larger ERP. The runtime stack is **FastAPI + SQLAlchemy 2.0 + PostgreSQL 15** (via Docker). The Alembic migration history is a single linear chain:

```
aeaadc4f2374 → e47081302c4e → 0d633dc08f98 → 0f8db8a263c5
            → e5f8a91c0d4e → b7d9f2a1c3e4 → c8e1a4b6d2f7
            → d3f5a7c9e1b2
```

Where this document disagrees with the code, **the code is the source of truth** (per `CLAUDE.md`).

---

## 1. What This Service Does (Scope)

The Timetable Generator is a **standalone, multi-domain scheduling service** that manages schedulable resources, runs a constraint-driven solver to produce candidate timetables, and lets an admin select and publish one. It owns its auth, schema, and audit trail.

Planned timetable types (one engine, multiple `TimetableType` values):

| Timetable Type         | Description                                               |
|------------------------|-----------------------------------------------------------|
| Class Timetable        | Subject-wise weekly schedule per division/year (primary) |
| Faculty Timetable      | Consolidated teaching schedule per teacher                |
| Room Utilization Chart | Which rooms are occupied when                             |
| Event / Seminar Schedule | One-off or recurring special sessions                  |
| Industry Program (IP)  | Company visits, internship slots, industry lectures       |
| Exam Timetable         | Mid-sem, end-sem, viva, practicals                        |
| Lab Schedule           | Equipment-bound sessions needing specific rooms           |

All types share the same **constraint engine** and **resource pool**, ensuring zero conflicts across timetable types. Today the engine and weekly templates are first-class; date-bound types (events, exams, IP) reuse the same primitives (slot, room, faculty, group) but do not yet materialise calendar dates.

---

## 2. Core Concepts

### 2.1 Resources
Everything schedulable is a "resource". Resources can conflict with each other.

- **People:** Teachers, Guest Lecturers, Industry Experts
- **Spaces:** Classrooms, Labs, Seminar Halls, Auditoriums, Open Spaces
- **Groups:** Divisions, Batches, Single Years, Whole Departments
- **Equipment:** Projectors, Specialized Lab Equipment (linked to rooms)

### 2.2 Constraints
Rules the engine must obey. Two types:

- **Hard Constraints:** Inviolable. Generation fails if these are broken.
- **Soft Constraints:** Preferences. Scored and weighted. Engine optimizes to satisfy as many as possible.

### 2.3 Profiles
A **Profile** is a named, saveable bundle of: resources + constraints + parameters + scope. Think of it like a "preset" for a particular context (e.g., "CS Dept Full Semester", "FE Year Event Week").

### 2.4 Instances
Every generation run produces **multiple candidate timetables** (instances). The admin picks one, or edits and merges. No auto-commit.

---

## 3. Database Schema (PostgreSQL 15)

The backend uses SQLAlchemy 2.0 mapped-column models on PostgreSQL. This section lists every table the application defines, in the order they were added by Alembic. **The Alembic migrations are the source of truth** for column types — the snippets below are a human-readable guide, not a literal `CREATE TABLE` to copy.

**Migration chain (single linear, head = `e9f4a2b6d8c0`):**

```
aeaadc4f2374   initial tables (faculty, rooms, student_groups, subjects, faculty_availability, room_blackouts)
   → e47081302c4e   profiles + parameters + combinations
   → 0d633dc08f98   hard / soft constraints
   → 0f8db8a263c5   generations + instances + slots + history + reset log
   → e5f8a91c0d4e   subject_assignments + college_settings (Phase 1 mappings)
   → b7d9f2a1c3e4   constraint_type → VARCHAR(100) (no longer a native enum)
   → c8e1a4b6d2f7   room_blackouts.day_of_week (recurring blackouts)
   → d3f5a7c9e1b2   audit_logs
   → e9f4a2b6d8c0   faculty_availability effective dates nullable
```

There are **22 tables** registered with `Base.metadata` (all exported from `app/models/__init__.py`): `admins`, `faculty`, `rooms`, `student_groups`, `subjects`, `faculty_availability`, `room_blackouts`, `subject_assignments`, `college_settings`, `timetable_profiles`, `profile_resources`, `profile_parameters`, `profile_combinations`, `profile_combination_members`, `hard_constraints`, `soft_constraints`, `timetable_generations`, `timetable_instances`, `timetable_slots`, `timetable_history`, `timetable_reset_log`, plus `audit_logs`.

### 3.1 Resource & Auth Tables

```sql
-- ADMIN (auth + RBAC)
CREATE TABLE admins (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    email       VARCHAR(100) NOT NULL UNIQUE,
    password    VARCHAR(255) NOT NULL,        -- bcrypt hash
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

-- FACULTY (schedulable resource)
CREATE TABLE faculty (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(100) NOT NULL,
    email               VARCHAR(100) NOT NULL UNIQUE,
    department          VARCHAR(100) NOT NULL,           -- free-text (no FK to a departments table)
    max_hours_per_week  INTEGER NOT NULL DEFAULT 20,
    max_hours_per_day   INTEGER NOT NULL DEFAULT 5,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE
);

-- SUBJECTS
CREATE TABLE subjects (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    subject_code    VARCHAR(20) NOT NULL UNIQUE,
    department      VARCHAR(100) NOT NULL,               -- free-text
    semester        INTEGER NOT NULL,
    hours_per_week  INTEGER NOT NULL,
    requires_lab    BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- ROOMS & SPACES
CREATE TABLE rooms (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,               -- "Lab 3", "Seminar Hall A"
    room_code       VARCHAR(20) NOT NULL UNIQUE,
    room_type       roomtype NOT NULL,                   -- CLASSROOM | LAB | SEMINAR_HALL | AUDITORIUM
    capacity        INTEGER NOT NULL,
    floor           INTEGER,
    building        VARCHAR(50),
    has_projector   BOOLEAN NOT NULL DEFAULT FALSE,
    has_ac          BOOLEAN NOT NULL DEFAULT FALSE,
    -- NOTE: equipment_json is NOT in the current schema; that field is a future
    -- extension tracked in plan.md under "Generic resource requirements".
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);
-- NOTE: the doc previously listed OPEN_SPACE / CONFERENCE room_type values; the
-- RoomType enum currently shipped only carries the four above.

-- ROOM BLACKOUTS (maintenance, reserved dates)
-- Either date-specific (`date` set — for the eventual date materialiser) or
-- recurring by weekday (`day_of_week` set — enforced by the constraint checker
-- against the weekly templates today). Both columns are nullable, but the
-- checker currently matches by `day_of_week` only.
CREATE TABLE room_blackouts (
    id           SERIAL PRIMARY KEY,
    room_id      INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    date         DATE,                                  -- set for a one-off date
    day_of_week  SMALLINT,                              -- 0=Mon..6=Sun for a recurring blackout
    slot_start   TIME,
    slot_end     TIME,
    reason       VARCHAR(255)
);

-- FACULTY AVAILABILITY & PREFERENCES
-- A row is a *timeless* weekday rule when effective_from/effective_to are
-- NULL; with date bounds it only applies to the week anchored by the profile's
-- `term_start` parameter (see §8.8). The checker consults both.
CREATE TABLE faculty_availability (
    id              SERIAL PRIMARY KEY,
    faculty_id      INTEGER NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
    day_of_week     SMALLINT NOT NULL,                   -- 0=Mon, 6=Sun
    slot_start      TIME,                                -- nullable (all-day unavailability)
    slot_end        TIME,
    availability    availabilitytype NOT NULL,           -- AVAILABLE | UNAVAILABLE | PREFFERED  (sic — enum spelling)
    reason          VARCHAR(255),
    effective_from  DATE,                                -- NULL = unbounded / timeless
    effective_to    DATE
);

-- STUDENT GROUPS (divisions, batches, years)
CREATE TABLE student_groups (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,                   -- "CS-A", "FE-2025", "TE-Batch-2"
    group_type  grouptype NOT NULL,                     -- DIVISION | BATCH | YEAR | DEPARTMENT | CUSTOM
    department  VARCHAR(100) NOT NULL,                  -- free-text (no FK)
    year        INTEGER,
    semester    INTEGER,
    strength    INTEGER NOT NULL,                       -- student count
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);
-- NOTE: the doc previously listed `department_id INT NOT NULL` and
-- `parent_group_id INT` (hierarchical grouping); the actual model has neither.
-- Hierarchical grouping is tracked in plan.md as a future lever.

-- SUBJECT ↔ FACULTY ↔ GROUP MAPPING (Phase 1 — implemented)
-- The single source of truth for "who teaches what to which division";
-- the greedy solver expands each row into `weekly_hours` sessions.
CREATE TABLE subject_assignments (
    id           SERIAL PRIMARY KEY,
    subject_id   INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    faculty_id   INTEGER REFERENCES faculty(id) ON DELETE SET NULL,
    group_id     INTEGER NOT NULL REFERENCES student_groups(id) ON DELETE CASCADE,
    weekly_hours INTEGER NOT NULL DEFAULT 1,
    load_share   FLOAT NOT NULL DEFAULT 1.0              -- e.g. 0.8/0.2 shared teaching
);

-- COLLEGE SETTINGS SINGLETON (Phase 1 — implemented)
-- One row (id=1), auto-created on startup and lazily by `get_settings()`.
-- Per-college feature flags the engine reads at generation time; `config_json`
-- holds free-form tunables (e.g. `max_cross_dept_per_day`).
CREATE TABLE college_settings (
    id                              INTEGER PRIMARY KEY,        -- always 1; not DB-enforced
    enable_lab_batches              BOOLEAN NOT NULL DEFAULT FALSE,
    allow_cross_dept_subjects       BOOLEAN NOT NULL DEFAULT FALSE,
    enable_soft_constraint_scoring  BOOLEAN NOT NULL DEFAULT TRUE,
    config_json                     JSON                        -- e.g. {"max_cross_dept_per_day": 2}
);

-- AUDIT LOGS (mutation trail from the observability middleware)
CREATE TABLE audit_logs (
    id           SERIAL PRIMARY KEY,
    method       VARCHAR(10) NOT NULL,                    -- POST / PUT / PATCH / DELETE
    path         VARCHAR(300) NOT NULL,
    status_code  INTEGER NOT NULL,
    admin_id     INTEGER REFERENCES admins(id),            -- nullable when unauthenticated
    request_id   VARCHAR(32),
    created_at   TIMESTAMP
);
CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);
```

### 3.2 Profile & Parameter Tables

```sql
-- PROFILES (named parameter bundles)
CREATE TABLE timetable_profiles (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL,
    description     TEXT,
    scope_type      scopetype NOT NULL,                    -- DEPARTMENT | YEAR | DIVISION | EVENT | EXAM | CUSTOM
    academic_year   VARCHAR(10) NOT NULL,                  -- "2025-26"
    semester        INTEGER,
    department      VARCHAR(100),                          -- free-text; no FK; no updated_at column
    created_by      INTEGER NOT NULL REFERENCES admins(id),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_archived     BOOLEAN NOT NULL DEFAULT FALSE,
    last_used_at    TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
-- NOTE: `department_id INT` (FK) and `updated_at ON UPDATE CURRENT_TIMESTAMP`
-- from earlier docs do NOT exist in the current schema.

-- PROFILE ↔ RESOURCE MAPPINGS (which rooms, faculty, groups, subjects belong
-- to a profile). `resource_id` is polymorphic by `resource_type` — there is
-- no DB-level FK, so the engine must validate.
CREATE TABLE profile_resources (
    id            SERIAL PRIMARY KEY,
    profile_id    INTEGER NOT NULL REFERENCES timetable_profiles(id) ON DELETE CASCADE,
    resource_type  resourcetype NOT NULL,                  -- ROOM | FACULTY | STUDENT_GROUP | SUBJECT
    resource_id   INTEGER NOT NULL
);

-- PROFILE COMBINATIONS (profiles merged together for a run — currently
-- stored only; the scheduler does not yet resolve combination members;
-- generation accepts `combination_id` and stores it, but still uses one
-- `profile_id`. See §5.1 step 1.)
CREATE TABLE profile_combinations (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(150),
    created_by  INTEGER NOT NULL REFERENCES admins(id),
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE profile_combination_members (
    combination_id  INTEGER NOT NULL REFERENCES profile_combinations(id),
    profile_id      INTEGER NOT NULL REFERENCES timetable_profiles(id),
    weight          DECIMAL(3,2) NOT NULL DEFAULT 1.00,    -- relative priority if conflicts
    PRIMARY KEY (combination_id, profile_id)
);

-- PARAMETERS (key-value store per profile, typed)
CREATE TABLE profile_parameters (
    id           SERIAL PRIMARY KEY,
    profile_id   INTEGER NOT NULL REFERENCES timetable_profiles(id) ON DELETE CASCADE,
    param_key    VARCHAR(100) NOT NULL,
    param_value  TEXT NOT NULL,
    param_type   paramtype NOT NULL,                       -- INT | FLOAT | STRING | BOOLEAN | TIME | JSON
    description  VARCHAR(300),
    UNIQUE (profile_id, param_key)
);
```

#### Standard Parameter Keys (seeded defaults)

| param_key                  | type    | example value           |
|----------------------------|---------|-------------------------|
| `slot_duration_minutes`    | INT     | 60                      |
| `slots_per_day`            | INT     | 7                       |
| `day_start_time`           | STRING  | `"09:00"` (first slot start, "HH:MM") |
| `working_days`             | JSON    | `["MON","TUE","WED","THU","FRI"]` |
| `term_start`               | STRING  | `"2025-01-06"` (anchor for calendar-date rules, see §8.8) |
| `lunch_break_after_slot`   | INT     | 3                       |
| `lunch_break_duration_minutes` | INT | 60                      |
| `max_consecutive_lectures` | INT     | 3                       |
| `max_daily_load_teacher`   | INT     | 5                       |
| `min_gap_between_exams`    | INT     | 1 (days)                |
| `lab_slot_duration_minutes`| INT     | 120                     |
| `allow_saturday`           | BOOLEAN | false                   |
| `buffer_slots_per_day`     | INT     | 1                       |
| `max_room_utilization_pct` | FLOAT   | 0.85                    |

### 3.3 Constraint Tables

```sql
-- HARD CONSTRAINTS (must not be violated)
CREATE TABLE hard_constraints (
    id              SERIAL PRIMARY KEY,
    profile_id      INTEGER REFERENCES timetable_profiles(id),    -- NULL = global
    constraint_type VARCHAR(100) NOT NULL,                         -- string, not enum (see below)
    config_json     JSON,
    description     VARCHAR(300),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- SOFT CONSTRAINTS (scored, engine tries to satisfy)
CREATE TABLE soft_constraints (
    id              SERIAL PRIMARY KEY,
    profile_id      INTEGER REFERENCES timetable_profiles(id),    -- NULL = global
    constraint_type VARCHAR(100) NOT NULL,
    config_json     JSON,
    weight          DECIMAL(4,2) NOT NULL DEFAULT 1.00,           -- higher = more important
    description     VARCHAR(300),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);
```

#### Built-In Constraint Types

The `ConstraintType` enum (`app/models/constraints.py`) is a **catalog only** —
input validation and discovery, not a DB enum. The `constraint_type` column
has been `VARCHAR(100)` since migration `b7d9f2a1c3e4` so a new data-driven
rule can be added without a schema migration.

**Hard — structural (always-on in `ConstraintChecker`):**

| Type                              | Where                                                |
|-----------------------------------|------------------------------------------------------|
| `NO_TEACHER_DOUBLE_BOOK`          | `_check_teacher_double_book`                         |
| `NO_ROOM_DOUBLE_BOOK`             | `_check_room_double_book`                            |
| `NO_GROUP_DOUBLE_BOOK`            | `_check_group_double_book`                           |
| `ROOM_CAPACITY_SUFFICIENT`        | `_check_room_capacity`                               |
| `ROOM_TYPE_MATCH`                 | `_check_room_type_match`                             |
| `RESPECT_TEACHER_UNAVAILABILITY`  | `_check_teacher_availability` (consults `effective_from`/`effective_to` vs the slot's materialized date) |
| `RESPECT_ROOM_BLACKOUT`           | `_check_room_blackout` (recurring weekday always; date-specific only when the slot carries a materialized `slot_date`) |
| `FACULTY_MAX_HOURS_PER_DAY`       | `_check_faculty_load`                                |
| `FACULTY_MAX_HOURS_PER_WEEK`      | `_check_faculty_load`                                |
| `NO_CROSS_TIMETABLE_TEACHER_CONFLICT` | `_check_published_conflicts`                     |
| `NO_CROSS_TIMETABLE_ROOM_CONFLICT`    | `_check_published_conflicts`                     |
| `NO_CROSS_TIMETABLE_GROUP_CONFLICT`   | `_check_published_conflicts`                     |
| `SAME_SUBJECT_SAME_DAY`           | `_check_same_subject_same_day`                       |
| `CROSS_DEPT_DAILY_CAP`            | `_check_cross_dept_cap` (driven by `config_json.max_cross_dept_per_day`) |

**Hard — data-driven (registry in `app/engine/constraint_registry.py`):**

| Type                              | config_json keys                                            | Validator                          |
|-----------------------------------|-------------------------------------------------------------|------------------------------------|
| `SUBJECT_TIME_PREFERENCE`         | `subject_id?`, `max_slot?`, `min_slot?`, `period?`, `boundary_slot?` | `_subject_time_preference`     |
| `MAX_CONSECUTIVE_SAME_TEACHER`    | `max`, `faculty_id?`                                        | `_max_consecutive_same_teacher`    |
| `TEACHER_YEAR_RESTRICTION`        | `faculty_id`, `allowed_years`                               | `_teacher_year_restriction`        |
| `LAB_BATCH_ROTATION`              | `group_days: {"<group_id>": [day_of_week, ...]}`            | `_lab_batch_rotation`              |

**Soft (scorers in `app/engine/scorer.py`; CP-SAT objective builders in `app/engine/soft_objective.py`):**

| Type                              | Scorer implemented? | CP-SAT objective? | config_json keys                              |
|-----------------------------------|---------------------|-------------------|-----------------------------------------------|
| `TEACHER_PREFERS_MORNING`         | ✅ yes              | ✅ yes            | `faculty_id?`, `boundary_slot?` (default 4)   |
| `MINIMIZE_STUDENT_FREE_SLOTS`     | ✅ yes              | ✅ yes            | `{}`                                          |
| `AVOID_CONSECUTIVE_SAME_SUBJECT`  | ❌ no               | ❌ no             | —                                             |
| `MINIMIZE_TEACHER_FREE_SLOTS`     | ❌ no               | ❌ no             | —                                             |
| `DISTRIBUTE_SUBJECTS_EVENLY`      | ❌ no               | ❌ no             | —                                             |
| `BALANCE_TEACHER_LOAD`            | ❌ no               | ❌ no             | —                                             |

**Not implemented (catalogued but with no validator / scorer):**

- `EXAM_DATE_SEPARATION` (hard) — listed historically; no validator.
- `CONTIGUOUS_LAB_SLOTS` (hard) — listed historically; no validator. Today every session occupies exactly one slot; multi-slot labs are a future lever (`plan.md`).
- `TEACHER_SUBJECT_MATCH` (hard) — implicit, because the solver only generates sessions from `subject_assignments` rows, which already bind a faculty to a subject/group.

> The catalog (`ConstraintType` enum) is the single source of truth for what the API surface accepts in `GET /constraints/types` — the endpoint derives its hard/soft lists from `HARD_CONSTRAINT_TYPES` / `SOFT_CONSTRAINT_TYPES` (defined next to the enum in `app/models/constraints.py`), so a new enum member can never drift from discovery.

> Still hardcoded (structural) rather than registry-driven: the core double-booking / capacity / availability / faculty-load / cross-timetable checks. They could be moved into the registry as always-on entries later so *every* rule is uniform, but they are kept inline since they are non-negotiable and never per-profile.

#### Soft-Constraint Scoring (implemented — Phase 3)

Soft constraints don't fail a timetable — they *rank* it. `app/engine/scorer.py` mirrors the hard registry: `SOFT_CONSTRAINT_REGISTRY[type] = scorer`, where `scorer(slots, config, ctx) -> float` returns a satisfaction value in `[0, 1]` (1 = fully satisfied). After the solver finishes an instance, the scheduler computes a weighted mean of the active `soft_constraints` (using each row's `weight`) into one score in `[0, 1]` (**higher is better**), stores it on `instance.soft_score`, and records the best across instances on `generation.score_best_instance`. Gated by the `enable_soft_constraint_scoring` college flag.

When **no** soft rules apply (none defined for the profile, or none registered), `score_instance` returns `1.0` so the instance is treated as perfectly satisfied rather than left blank. The scheduler only calls `score_instance` when soft rules exist, so `generation.score_best_instance` stays `NULL` when the profile defines none.

**In CP-SAT, soft preferences are also an objective.** `app/engine/soft_objective.py` mirrors the scorer registry: `SOFT_OBJECTIVE_REGISTRY[type] = builder`, where a builder returns `(linear_expr, multiplier)` terms folded into `model.Maximize(...)` (scaled by the rule's `weight`). Placements stay strictly primary via `PLACEMENT_WEIGHT = 1000.0` per placed session, so a soft term can only break ties among solutions with the same placement count — never trade away a placed session. Gated by the same `enable_soft_constraint_scoring` flag, so scoring off ⇒ pure placement objective.

### 3.4 Generation & Output Tables

```sql
-- A SINGLE GENERATION RUN (one click of "Generate")
CREATE TABLE timetable_generations (
    id                  SERIAL PRIMARY KEY,
    profile_id          INTEGER REFERENCES timetable_profiles(id),
    combination_id      INTEGER REFERENCES profile_combinations(id),   -- stored, but not yet resolved
    academic_year       VARCHAR(10) NOT NULL,
    semester            SMALLINT,
    timetable_type      timetabletype NOT NULL,                       -- CLASS | FACULTY | ROOM | EVENT | EXAM | IP | CUSTOM
    generation_status   generationstatus NOT NULL DEFAULT 'PENDING',  -- PENDING | RUNNING | COMPLETED | FAILED
    algorithm_used      algorithmtype NOT NULL DEFAULT 'GREEDY',      -- native enum (not VARCHAR(50))
    score_best_instance FLOAT,                                        -- best soft score; NULL when no soft rules
    instances_requested INTEGER NOT NULL DEFAULT 3,
    instances_produced  INTEGER NOT NULL DEFAULT 0,
    run_duration_ms     INTEGER,                                      -- set by the router after the fact
    triggered_by        INTEGER NOT NULL REFERENCES admins(id),
    triggered_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMP,
    error_log           TEXT
);

-- ONE CANDIDATE OUTPUT FROM A GENERATION RUN
CREATE TABLE timetable_instances (
    id              SERIAL PRIMARY KEY,
    generation_id   INTEGER NOT NULL REFERENCES timetable_generations(id),
    instance_number INTEGER NOT NULL,                                 -- 1, 2, 3...  (Integer, not TINYINT)
    label           VARCHAR(100),
    soft_score      FLOAT,                                            -- weighted mean in [0,1]; see §3.3
    hard_violations INTEGER NOT NULL DEFAULT 0,
    status          instancestatus NOT NULL DEFAULT 'DRAFT',          -- DRAFT | SELECTED | PUBLISHED | ARCHIVED
    selected_by     INTEGER REFERENCES admins(id),
    selected_at     TIMESTAMP,
    published_at    TIMESTAMP,
    notes           TEXT
);

-- INDIVIDUAL SLOTS IN AN INSTANCE (the actual timetable entries)
CREATE TABLE timetable_slots (
    id                SERIAL PRIMARY KEY,
    instance_id       INTEGER NOT NULL REFERENCES timetable_instances(id) ON DELETE CASCADE,
    slot_date         DATE,                                           -- for one-off events/exams (not materialised yet)
    day_of_week       SMALLINT,                                       -- for recurring weekly schedule
    slot_number       INTEGER NOT NULL,
    start_time        TIME NOT NULL,
    end_time          TIME NOT NULL,
    subject_id        INTEGER REFERENCES subjects(id),
    faculty_id        INTEGER REFERENCES faculty(id),
    room_id           INTEGER REFERENCES rooms(id),
    student_group_id  INTEGER REFERENCES student_groups(id),
    session_type      sessiontype NOT NULL,                           -- LECTURE | LAB | TUTORIAL | SEMINAR | EVENT | EXAM | IP | FREE
    is_manual_override BOOLEAN NOT NULL DEFAULT FALSE,
    override_reason   VARCHAR(300),
    external_speaker  VARCHAR(200),                                   -- guest lectures / IP
    notes             TEXT,
    created_at        TIMESTAMP NOT NULL DEFAULT NOW()
);
-- NOTE: the doc previously listed composite indexes
-- (idx_instance_day / idx_faculty_slot / idx_group_slot); the current schema
-- does not create them. With small instance sizes this is fine; revisit when
-- slot counts grow.
```

### 3.5 History & Reset Tables

```sql
-- PUBLISHED TIMETABLE ARCHIVE (immutable historical record)
CREATE TABLE timetable_history (
    id                  SERIAL PRIMARY KEY,
    original_instance_id INTEGER NOT NULL,
    academic_year       VARCHAR(10) NOT NULL,
    semester            SMALLINT,
    snapshot_json       JSON NOT NULL,                                -- full denormalized snapshot
    archived_by         INTEGER NOT NULL REFERENCES admins(id),
    archived_at         TIMESTAMP NOT NULL DEFAULT NOW(),
    archive_reason      archivereason NOT NULL                        -- YEAR_RESET | SEMESTER_END | MANUAL | SUPERSEDED
);

-- ANNUAL RESET LOG
CREATE TABLE timetable_reset_log (
    id              SERIAL PRIMARY KEY,
    reset_type      resettype NOT NULL,                               -- FULL_YEAR | SEMESTER | PROFILE_SPECIFIC
    academic_year   VARCHAR(10) NOT NULL,
    profiles_reset  JSON,                                             -- {"profile_ids": [...]}
    reset_by        INTEGER NOT NULL REFERENCES admins(id),
    reset_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    notes           TEXT
);
-- NOTE: the doc previously listed `snapshot_json LONGTEXT`; the actual column
-- is JSON (Postgres native). `LONGTEXT` is a MySQL type and never applied here.

---

## 4. API Design (FastAPI)

### 4.1 Project Structure

```
timetable-api/
├── main.py                          # FastAPI app, middleware, audit, /health
├── config.py                        # pydantic-settings (DB_*, SECRET_KEY, ALGORITHM)
├── database.py                      # SQLAlchemy engine + SessionLocal + Base
├── models/                          # SQLAlchemy 2.0 mapped-column models (one file per entity)
│   ├── admin.py
│   ├── audit.py
│   ├── constraints.py               # HardConstraint, SoftConstraint + ConstraintType enum (catalog)
│   ├── faculty.py                   # Faculty, FacultyAvailability + AvailabilityType
│   ├── generation.py                # TimetableGeneration, TimetableInstance, TimetableSlot + enums
│   ├── groups.py                    # StudentGroup + GroupType
│   ├── history.py                   # TimetableHistory, TimetableResetLog
│   ├── profiles.py                  # TimetableProfile, ProfileResource, ProfileParameter,
│   │                                # ProfileCombination, ProfileCombinationMember
│   ├── rooms.py                     # Room, RoomBlackout + RoomType
│   ├── settings.py                  # CollegeSettings (singleton)
│   ├── subject_assignments.py       # SubjectAssignment
│   └── subjects.py                  # Subject
├── schemas/                         # Pydantic Create/Update/Response per entity
├── router/                          # FastAPI APIRouter per entity (one file each)
│   ├── auth.py                      # /auth/register, /auth/login
│   ├── audit.py                     # GET /audit/  (read the mutation trail)
│   ├── assignments.py               # /assignments CRUD  (subject ↔ faculty ↔ group)
│   ├── constraints.py               # /constraints/hard, /constraints/soft, /constraints/types
│   ├── export.py                    # /export/instances/{id}/{pdf,csv,ical}
│   ├── faculty.py                   # /faculty CRUD
│   ├── faculty_availibility.py      # /faculty_availability CRUD  (filename typo, prefix is correct)
│   ├── generate.py                  # POST /generate, GET /generate/{id}/status
│   ├── groups.py                    # /groups CRUD
│   ├── history.py                   # /history CRUD
│   ├── import_csv.py                # POST /import/{rooms,faculty,groups,subjects}
│   ├── instances.py                 # /instances/{generation_id}, /{instance_id}/{slots,select,publish}
│   ├── profiles.py                  # /profiles CRUD + /combine
│   ├── reset.py                     # POST /reset, GET /reset/log
│   ├── room_blackout.py             # /blackouts CRUD
│   ├── rooms.py                     # /rooms CRUD
│   ├── settings.py                  # /settings/ GET/PUT
│   └── subjects.py                  # /subjects CRUD
├── engine/
│   ├── scheduler.py                 # Scheduler.run() orchestrator
│   ├── constraint_checker.py        # ConstraintChecker, SlotCandidate, ConstraintViolation
│   ├── constraint_registry.py       # HARD_CONSTRAINT_REGISTRY + @hard_rule
│   ├── scorer.py                    # SOFT_CONSTRAINT_REGISTRY + score_instance()
│   ├── soft_objective.py            # CP-SAT objective builders for soft rules (OR-Tools)
│   └── solvers/
│       ├── greedy_solver.py         # GreedySolver, SessionToSchedule
│       └── or_tools_solver.py       # ORToolsSolver (CP-SAT)
├── services/
│   ├── settings_service.py          # get_settings(), update_settings() — singleton helper
│   └── export_service.py            # PDF (ReportLab), CSV, RFC 5545 iCal + get_filtered_slots
├── tasks/                           # (placeholder; async generation is future work)
├── tests/
│   ├── conftest.py                  # FastAPI TestClient over in-memory SQLite
│   ├── test_runner.py               # @suite / @test decorators, seed_minimal()
│   └── test_settings_and_assignments.py
└── utils/
    ├── auth.py                      # bcrypt (direct), JWT, get_current_admin
    └── pagination.py                # Pagination dataclass + paginate()
```

The `engine/` tree intentionally does **not** have a `conflict_detector.py` or
`genetic_solver.py` — cross-timetable conflicts live in `Scheduler._load_published_conflicts()`
+ `ConstraintChecker._check_published_conflicts()`, and only two solvers exist
(greedy + OR-Tools). See §5 for the wiring.

### 4.2 Core Endpoints

The route prefixes below match the `@router.prefix` declarations in the router files. Every mutating endpoint depends on `get_current_admin` (JWT bearer); list/get endpoints on resources are public by default. Pagination (`?page=`, `?limit=`) is wired through `app/utils/pagination.py` on list endpoints where the router imports it.

#### Resource Management

```
GET    /rooms                          List rooms (filter: room_type, min_capacity, building)
GET    /rooms/{id}                     Get one room
POST   /rooms                          Create room
PUT    /rooms/{id}                     Update room
DELETE /rooms/{id}                     Soft delete (is_active=false)

GET    /faculty                        List faculty (filter: department)
GET    /faculty/{id}                   Get one faculty
POST   /faculty                        Create faculty (email unique)
PUT    /faculty/{id}                   Update faculty
DELETE /faculty/{id}                   Soft delete (is_active=false)

GET    /subjects                       List subjects (filter: semester, department, requires_lab)
GET    /subjects/{id}                  Get one subject
POST   /subjects                       Create subject (subject_code unique)
PUT    /subjects/{id}                  Update subject
DELETE /subjects/{id}                  Soft delete (is_active=false)

GET    /groups                         List student groups (filter: year, department, group_type)
GET    /groups/{id}                    Get one group
POST   /groups                         Create group
DELETE /groups/{id}                    Soft delete (is_active=false)
                                        # NOTE: no PUT /groups/{id} currently — add if needed.

GET    /blackouts                      List room blackouts
GET    /blackouts/{id}                 Get one blackout
POST   /blackouts                      Create a blackout window for a room
PUT    /blackouts/{id}                 Update blackout
DELETE /blackouts/{id}                 Hard delete
                                        # NOTE: blackouts are NOT nested under /rooms/{id};
                                        # `room_id` is a field on the blackout body.

GET    /faculty_availability           List faculty availability rows
GET    /faculty_availability/{id}      Get one row (by row id, NOT by faculty_id)
POST   /faculty_availability           Create availability window
PUT    /faculty_availability/{id}      Update availability row
DELETE /faculty_availability/{id}      Hard delete
                                        # NOTE: prefix is `/faculty_availability` (underscore),
                                        # not `/faculty-availability` (dash). The router file
                                        # has a typo'd name `faculty_availibility.py`.
```

#### Subject Assignments & College Settings (Phase 1 — implemented)

```
GET    /assignments                    List subject↔faculty↔group rows (filter: subject_id, faculty_id, group_id; paginated)
GET    /assignments/{id}               Get one row
POST   /assignments                    Create mapping (validates subject/faculty/group exist)
PUT    /assignments/{id}               Update faculty / weekly_hours / load_share
DELETE /assignments/{id}               Hard delete

GET    /settings/                      Read the college feature-flag singleton (auto-creates row id=1)
PUT    /settings/                      Update one or more flags / config_json

POST   /auth/register                  Create an admin (email + name unique)
POST   /auth/login                     Returns {"access_token", "token_type": "bearer"}

POST   /import/rooms                   Bulk import rooms via CSV (multipart file)
POST   /import/faculty                 Bulk import faculty via CSV
POST   /import/groups                  Bulk import student groups via CSV
POST   /import/subjects                Bulk import subjects via CSV
                                        # All four are all-or-nothing: any invalid row rejects
                                        # the whole file (422, inserted=0) so the DB never ends
                                        # up holding rows the response didn't report. room_code /
                                        # email / subject_code are required and checked for
                                        # duplicates within the file AND against the DB.

GET    /health                         Liveness + DB reachability (for deploy monitors)
```

#### Profile Management

```
GET    /profiles                       List profiles (filter: academic_year, scope_type, department, is_archived)
GET    /profiles/{id}                  Get one profile
POST   /profiles                       Create profile (created_by = current admin)
PUT    /profiles/{id}                  Update profile
DELETE /profiles/{id}                  Soft delete (is_archived=true, is_active=false)

GET    /profiles/{id}/resources        List resources attached to a profile
POST   /profiles/{id}/resources        Add a resource (room / faculty / group / subject)
DELETE /profiles/{id}/resources/{resource_id}   Remove a resource

GET    /profiles/{id}/parameters       List parameters for a profile
POST   /profiles/{id}/parameters       Upsert by (profile_id, param_key)
DELETE /profiles/{id}/parameters/{param_key}    Remove a parameter

POST   /profiles/combine               Create a profile_combination + members
                                        # NOTE: combination rows are stored but the scheduler
                                        # does not yet resolve them — see §5.1 step 1.
                                        # There is no GET /profiles/combinations list and no
                                        # /profiles/combinations/{id}/resolve endpoint yet;
                                        # those are tracked in plan.md.
```

#### Constraint Management

```
GET    /constraints/hard               List active hard constraints (filter: profile_id)
POST   /constraints/hard               Create hard constraint
PUT    /constraints/hard/{id}          Update hard constraint
DELETE /constraints/hard/{id}          Soft delete (is_active=false)

GET    /constraints/soft               List active soft constraints (filter: profile_id)
POST   /constraints/soft               Create soft constraint with weight
PUT    /constraints/soft/{id}          Update soft constraint
DELETE /constraints/soft/{id}          Soft delete

GET    /constraints/types              Discovery: hard + soft type catalogs
                                        # NOTE: this endpoint currently returns a hardcoded list
                                        # that lags the registry; regenerate from the catalog
                                        # when it grows.
```

#### Generation (Core)

```
POST   /generate                       Trigger a generation run (synchronous)
  Body: {
    profile_id OR combination_id,                  # combination_id is stored but not yet resolved
    timetable_type,
    academic_year,
    semester,
    instances_requested: 3,                         # how many options to produce
    algorithm: "OR_TOOLS" | "GREEDY",               # OR_TOOLS requires `uv add ortools`
    respect_existing_published: true                # always honoured: Scheduler._load_published_conflicts
  }
  Response: 201 with the TimetableGeneration row (status=COMPLETED on success).

GET    /generate/{run_id}/status       Poll a run (PENDING/RUNNING/COMPLETED/FAILED)
                                        # NOTE: there is no GET /generate/{run_id}/instances
                                        # or /generate/{run_id}/instances/{inst_id} endpoint;
                                        # instance listing lives at /instances/{generation_id}
                                        # and slot detail at /instances/{instance_id}/slots.
```

#### Instance Actions

```
GET    /instances/{generation_id}      List every instance for a generation run
GET    /instances/{instance_id}/slots  List every slot of an instance (ordered by day, slot)
POST   /instances/{instance_id}/select Mark an instance as SELECTED (records selected_by/_at)
POST   /instances/{instance_id}/publish  Publish (status=PUBLISHED); archives previously
                                        # PUBLISHED instances of the SAME generation; published
                                        # instances from other generations remain live and feed
                                        # cross-timetable reservations on the next run.
PATCH  /instances/{instance_id}/slots/{slot_id}   Manual override of a slot
                                        # Sets is_manual_override=true and override_reason.
                                        # The new position is re-validated by the constraint
                                        # checker first — a conflict returns 409 and the slot
                                        # is left untouched.
                                        # NOTE: there is no DELETE /instances/{id}/slots/{slot_id}
                                        # (no "remove slot, create FREE" endpoint yet), and no
                                        # /instances/{id}/conflicts, /instances/{id}/diff/{other},
                                        # or /instances/{id}/clone. Those are tracked in plan.md.
```

#### Export (implemented — filters on all three)

```
GET    /export/instances/{id}/pdf     Timetable grid as PDF (ReportLab, landscape A4)
GET    /export/instances/{id}/csv     Rows as CSV
GET    /export/instances/{id}/ical    Weekly-recurring .ics calendar (RFC 5545)
    # shared query filters (any combination):
    #   ?group_id=   one division      ?faculty_id= one teacher's schedule
    #   ?year=       a whole year       ?department= a department
    # iCal only: ?term_start=YYYY-MM-DD&term_end=YYYY-MM-DD  (anchor + RRULE UNTIL)
    # An empty filter result is a 404 for CSV/iCal (PDF renders an empty grid).
```

#### History & Reset

```
GET    /history                        List archived snapshots (filter: academic_year)
GET    /history/{id}                   View one archived snapshot (returns snapshot_json)
                                        # NOTE: no POST /history/restore/{id} yet — tracked in plan.md.

POST   /reset                          Trigger reset
  Body: {
    reset_type: "FULL_YEAR" | "SEMESTER" | "PROFILE_SPECIFIC",
    academic_year: "2025-26",
    profile_ids: [...],                # required for PROFILE_SPECIFIC
    notes: "..."
  }
GET    /reset/log                      View reset history
```

#### Audit

```
GET    /audit                          List most-recent-first audit entries
                                        # Filters: ?method=, ?admin_id=, ?status_code=
                                        # Paginated.
                                        # The audit middleware writes to /audit_logs for
                                        # every POST / PUT / PATCH / DELETE request.
```

---

## 5. The Scheduling Engine

### 5.1 How It Works (High Level)

`POST /generate` is **synchronous** — it returns when the solver finishes. The full flow lives in `Scheduler.run()` (`app/engine/scheduler.py`) plus a thin wrapper in `app/router/generate.py` that stamps `run_duration_ms` after the scheduler returns.

Step-by-step:

1. **Load Profile.** `SELECT * FROM timetable_profiles WHERE id=? AND is_active=true`. Then load `profile_resources`, `profile_parameters`, active `hard_constraints` and (if scoring is enabled) active `soft_constraints`. **`combination_id` (if provided) is STORED on the generation row but `profile_combination_members` are NOT YET merged** — the scheduler always operates on a single `profile_id`. Combination resolution is tracked in `plan.md`.
2. **Cross-Timetable Conflict Loader.** `Scheduler._load_published_conflicts()` selects every `TimetableSlot` belonging to every `TimetableInstance` with `status=PUBLISHED` and builds per-resource reserved sets:
   ```
   {"faculty": {(faculty_id, day_of_week, slot_number), ...},
    "room":    {(room_id,    day_of_week, slot_number), ...},
    "group":   {(group_id,   day_of_week, slot_number), ...}}
   ```
   Splitting per resource (rather than a single 5-way tuple) means a published booking blocks the faculty, room, or group at that time slot REGARDLESS of the other dimensions.
3. **Build Sessions to Schedule.** From `subject_assignments` rows, expand each `(subject, faculty, group, weekly_hours, load_share)` into `weekly_hours` `SessionToSchedule` objects. Each session carries `session_type` (`LECTURE` / `LAB` from `requires_lab`), an `is_cross_department` flag (`group.department != subject.department`), and is dropped if the `college_settings.allow_cross_dept_subjects` flag is off and the cross-dept flag is on.
4. **Solver Runs N times for N candidate instances.**
   - Instance #1: seed = `None` (deterministic baseline).
   - Instance #i (i > 0): seed = `i * 100 + attempt`.
   - For each attempt (up to `_DIVERSITY_ATTEMPTS = 6`): greedy shuffles `working_days` / `slot_times` / `rooms`; OR-Tools varies `solver.parameters.random_seed`.
   - Keep the first fingerprint whose Hamming distance from every already-accepted instance is ≥ `_DIVERSITY_MIN_DISTANCE = 1`; otherwise try the next seed. If all 6 attempts collide, the **last attempt** is kept (so a tiny problem still produces a result rather than a duplicate).
5. **Score & Rank.** If `enable_soft_constraint_scoring` is on AND there is at least one active soft rule, `score_instance(slots, soft_rules, ctx)` returns a weighted-mean satisfaction in `[0, 1]` and is stored on `instance.soft_score`; the best across instances is recorded on `generation.score_best_instance`. **With no soft rules at all**, `instance.soft_score` is left unset and `generation.score_best_instance` stays `NULL`. (For OR-Tools, the same soft rules are also folded into the CP-SAT objective — §5.2 — so the solver *pursues* them during search.)
6. **Commit & Return.** Scheduler sets `generation.status=COMPLETED`, `instances_produced`, `completed_at` and `db.commit()`s. The router (`POST /generate`) then stamps `run_duration_ms` on the model and returns it as the 201 response. The scheduler itself does NOT populate `error_log` on failure — the router catches `Exception` and turns it into a 500.

### 5.2 Solver Strategy

**Primary: Google OR-Tools CP-SAT** — *implemented* in `app/engine/solvers/or_tools_solver.py`.

- Industry-grade constraint satisfaction solver; select it with `algorithm="OR_TOOLS"` on `POST /generate` (greedy remains the default). Installed via `uv add ortools`.
- `ORToolsSolver` subclasses `GreedySolver` and overrides `solve()`, reusing the same session-building helpers. Constraint handling is split to match the `ConstraintChecker`:
  - **Per-candidate ("static") rules** — capacity, room type, recurring blackouts, teacher availability, cross-timetable reservations, and registry rules that don't depend on committed slots (`SUBJECT_TIME_PREFERENCE`, `LAB_BATCH_ROTATION`) — prune the variable domain by only creating `x[s, d, t, r]` variables that the checker accepts against an EMPTY committed set.
  - **Relational rules** — no teacher/room/group double-book, one-subject-per-group-per-day, per-faculty daily/weekly load — are added as CP-SAT constraints (`model.Add(sum(vs) <= 1)`).
- Objective: `model.Maximize(PLACEMENT_WEIGHT * sum(x.values()) + Σ soft_terms)` — maximise placed sessions first (`PLACEMENT_WEIGHT = 1000.0`), then optimise the active soft preferences via `app/engine/soft_objective.py` (`TEACHER_PREFERS_MORNING`, `MINIMIZE_STUDENT_FREE_SLOTS`; gated by `enable_soft_constraint_scoring`). Rules without a registered objective builder are skipped but still rank instances post-hoc.
- A final pass through the full checker (with the populated committed_slots) catches committed-dependent registry rules like `MAX_CONSECUTIVE_SAME_TEACHER` and `TEACHER_YEAR_RESTRICTION` that CP-SAT does not model. Such rules can only *drop* a placement; they cannot produce an invalid one.
- **Hard timeout: `ORToolsSolver.max_time_seconds = 5.0`** (class constant). There is **no `solver_timeout_seconds` profile parameter** — the 30-second value in older docs is illustrative only.

```python
# Simplified example of how OR-Tools is used in the engine
from ortools.sat.python import cp_model

model = cp_model.CpModel()

# One boolean variable per (session, day, slot, room) combination,
# pre-pruned by a static ConstraintChecker (empty committed set).
x = {}
for session in sessions:
    for day in working_days:
        for slot in slots:
            for room in rooms:
                x[session, day, slot, room] = model.NewBoolVar(
                    f"x_{session}_{day}_{slot}_{room}"
                )

# Hard constraint: each session placed at most once (== 1 after pruning)
for session in sessions:
    model.AddAtMostOne(
        x[session, d, t, r]
        for d in working_days for t in slots for r in rooms
    )

# Hard constraint: no room double booking
for day in working_days:
    for slot in slots:
        for room in rooms:
            model.AddAtMostOne(
                x[s, day, slot, room] for s in sessions
            )

# Soft preferences (TEACHER_PREFERS_MORNING, MINIMIZE_STUDENT_FREE_SLOTS) are
# folded into the objective by app/engine/soft_objective.py: each registered
# builder returns linear terms, scaled by the rule's weight, added on top of
# the placement sum. Instances are still ranked post-hoc by instance.soft_score
# via app/engine/scorer.py.

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 5.0   # ORToolsSolver.max_time_seconds
solver.parameters.randomize_search = True
status = solver.Solve(model)
```

**Fallback: Greedy Algorithm** — `app/engine/solvers/greedy_solver.py`.

- Used by default and when OR-Tools is unavailable. Validates every (session, day, slot, room) candidate with `ConstraintChecker.is_valid()` and commits the first that passes — **most-constrained first** (labs before non-labs, cross-department sessions last).
- Much faster, lower quality but always produces *something*.

**Optional: Genetic Algorithm** — *NOT implemented*.

The doc previously listed a third option ("Genetic Algorithm") with a `genetic_solver.py` file; **there is no such file** and `AlgorithmType` only has `GREEDY` and `OR_TOOLS`. If added later it will live in `app/engine/solvers/genetic_solver.py`.

### 5.3 Multiple Instances Strategy

**Implemented (seeded diversity filter).** Solvers are deterministic — re-running with no seed produces the same timetable. To generate meaningfully different candidates the scheduler treats **instance #1 as a deterministic baseline** (seed = `None`) and generates each later instance with a different seed:

- **Greedy** randomises the search order of `working_days`, `slot_times`, and `rooms` via `random.Random(seed).shuffle(...)`.
- **OR-Tools** sets `solver.parameters.random_seed = self.seed` and enables `randomize_search = True`.

The diversity filter compares fingerprints. For each instance:

1. Compute `_signature(slots) = frozenset({(student_group_id, day_of_week, slot_number, subject_id), ...})`.
2. Try up to `_DIVERSITY_ATTEMPTS = 6` seeds (`seed = i * 100 + attempt`).
3. Accept an attempt only if its symmetric-difference ("Hamming-style" distance) with every already-accepted signature is at least `_DIVERSITY_MIN_DISTANCE = 1` (i.e. at least one placement must differ).
4. If no attempt clears the threshold, the **last attempt** is kept (so a tiny problem still produces a result rather than an empty or duplicated instance).

> **Objective-based variation** (Instance #1 = best soft score, #2 = minimise teacher gaps, #3 = minimise student gaps, #4+ = random restarts) is **NOT implemented** — only the seed-driven diversity filter is. This is tracked as a future refinement in `plan.md`.

---

## 6. Profile System (Detailed)

### 6.1 Profile Scopes

The `ScopeType` enum (`app/models/profiles.py`) accepts **six** values:

```
DEPARTMENT  →  All years, all divisions, full semester  (most common — fully wired)
YEAR        →  Single year (e.g., only TE) — loads only that year's resources (wired)
DIVISION    →  Single section/class — minimal resource set (wired)
EVENT       →  One-time event parameters                  (catalog only — no solver branch)
EXAM        →  Exam-specific parameters                   (catalog only — no solver branch)
CUSTOM      →  User-defined combination                   (catalog only — no solver branch)
```

`DEPARTMENT`, `YEAR`, and `DIVISION` are the scopes the scheduler actually understands — they affect which `profile_resources` rows are loaded into the run. `EVENT`, `EXAM`, and `CUSTOM` are valid enum values for input validation but **share the same solver/registry path** as `DEPARTMENT` today; date-bound types (exam/event) reuse the primitive set as a regular `DEPARTMENT` profile with their `profile_resources` filtered to the relevant subset. There is no calendar-date materialisation on `timetable_slots` yet, so an exam timetable is just a weekly recurring grid.

### 6.2 Combining Profiles — *PARTIAL: tables exist, scheduler ignores `combination_id`*

The `profile_combinations` and `profile_combination_members` tables **do exist** (migration `e47081302c4e`) and `TimetableGeneration.combination_id` carries a foreign key to `profile_combinations.id`. However:

- The **scheduler does not read `combination_id`**. `Scheduler.run()` only expands the single `TimetableProfile` referenced by `TimetableGeneration.profile_id` — the combination members are not merged, weights are not consulted, and no per-rule resolution happens.
- There is **no `/profiles/combinations` router** (no `GET / POST / PUT / DELETE` for combinations) — the table is reachable only via direct SQL.
- `profile_combination_members.weight` is `DECIMAL(3,2)` (e.g., 0.60 for a 60/40 split) — a future use will probably use it for parameter merging.

If a future "Combine" feature is added, expected flows:

- A `POST /profiles/combinations` would create the combination + member rows.
- Conflict resolution would be one of:
  1. **Higher-weight member wins** (weight set in `profile_combination_members`)
  2. **Restrictive-merge** (e.g., for `max_daily_load_teacher`, take the minimum across members)
  3. **Admin-prompted** via `POST /profiles/combinations/{id}/resolve` (does not exist today)

### 6.3 Profile Shift — *NOT IMPLEMENTED*

"Shifting" means changing a profile's scope mid-session. The system would auto-save unsaved parameters, load the target profile's full state, and discard previous resources only on explicit confirmation.

This is **not implemented** — the frontend is responsible for switching which profile it holds in state; the backend treats each `GET /profiles/{id}` as an isolated read.

### 6.4 Annual Reset — *implemented*

`POST /reset/` (`app/router/reset.py`) accepts a `ResetRequest`:

```json
{
  "reset_type": "FULL_YEAR | SEMESTER | PROFILE_SPECIFIC",
  "academic_year": "2026-27",
  "profile_ids": [1, 2],     // required only for PROFILE_SPECIFIC
  "notes": "optional free text"
}
```

Actual behaviour per `reset_type`:

- **`FULL_YEAR`** — every `PUBLISHED` `timetable_instance` is **archived to `timetable_history`** via `_archive_instance()` (snapshot of slot rows + metadata, `archive_reason=YEAR_RESET`) and the instance status flips to `ARCHIVED`. Then every `timetable_profile` has its `profile_resources` and `profile_parameters` rows deleted and its `is_archived` flag set.
- **`PROFILE_SPECIFIC`** — only the named `profile_ids` get their resources/parameters cleared and `is_archived = True`. Published instances are **not** archived.
- **`SEMESTER`** — currently a no-op branch (not handled, falls through without archiving).

A `timetable_reset_log` row is **always** written with `reset_type`, `academic_year`, `profiles_reset = {"profile_ids": [...]}`, `reset_by`, `reset_at`, `notes`. Read it back via `GET /reset/log`.

> **Constraints are not touched.** `constraint_rules` (the `HardConstraint` / `SoftConstraint` rows) live in their own tables and are unaffected by reset — that is why earlier versions of this doc said "constraints are preserved year to year."

**There is no `archive_before_reset` flag, no `clear_parameters` toggle, and no `SEMESTER` branch logic.** All FULL_YEAR resets archive + clear; all PROFILE_SPECIFIC resets clear without archiving; SEMESTER is undefined.

---

## 7. Enterprise-Level Features

### 7.1 Async Generation with Job Queue — *NOT implemented*

Earlier planning called for Celery + Redis so the `POST /generate` request could return immediately and the long-running work (`Scheduler.run()` typically 1–10 seconds for moderate sizes, up to 30+ seconds for large departments) would be done by a worker.

**Today the endpoint is synchronous.** It blocks the HTTP request, runs `Scheduler.run()` inline, and returns the resulting `TimetableGeneration` row plus its instances. The full status flow is just:

```
POST /generate  →  generate router  →  Scheduler.run()  →  200 OK with full body
```

There is no `run_id` / `poll_url` / `PENDING` / `RUNNING` / `COMPLETED` status. If a future migration adds Celery, the expected shape is:

- `app/tasks/celery_tasks.py` — `run_timetable_generation(run_id)` worker.
- `app/router/generate.py` — `create_generation_run(db, request)` returning `PENDING` immediately, then `task.delay(...)`.
- `GET /generate/{run_id}/status` poll endpoint, plus an optional WebSocket.

### 7.2 Conflict Detection (Cross-Timetable) — *implemented, but NOT in `conflict_detector.py`*

There is no `app/engine/conflict_detector.py` file. Cross-timetable safety is implemented across two existing pieces:

- **`Scheduler._load_published_conflicts()`** (`app/engine/scheduler.py`) — at the start of generation, it queries every `PUBLISHED` `timetable_instance` across all generations and builds three `set[ResourceKey]` per resource kind:
  - `published_faculty`, `published_room`, `published_group`
  - each holding `{(id, day_of_week, slot_number)}` triples.
- **`ConstraintChecker._check_published_conflicts()`** — before committing any candidate, it lookups the resource ids in the corresponding set and rejects the placement if the triple is already taken.

The sets are split deliberately per resource type — a combined `(faculty, room, group, day, slot)` tuple would only refuse to place an identical five-way match and miss the real conflicts (same teacher, different room, etc.).

There is **no `GET /instances/{id}/conflicts` endpoint** — once a candidate passes the checker, there is no concept of reporting residual conflicts to the admin. The check is a hard gate, not a report.

### 7.3 Manual Override System — *implemented, re-validated*

- `PATCH /instances/{instance_id}/slots/{slot_id}` (`app/router/instances.py::override_slot`) lets an admin move a slot to a new `(day_of_week, slot_number, room_id)` and (optionally) swap to a different `faculty_id`. The request body is a `SlotOverride` (`app/schemas/generation.py`) and the endpoint:
  1. Loads the slot row scoped to that instance.
  2. Applies every supplied field via `setattr`.
  3. Re-validates the new position with a full `ConstraintChecker` pass (`app/router/instances.py::_revalidate_slot`) against the instance's other slots, the profile's registry rules, and the cross-timetable published reservations; a violation returns `409` and the slot is left untouched.
  4. Sets `is_manual_override = True` and stores `override_reason` (free-text audit trail).
- The `timetable_slots` table **does carry `is_manual_override`** (`Mapped[bool] default=False` in `app/models/generation.py`) and `override_reason: Mapped[Optional[str]]`.
- There is **no `DELETE /instances/{instance_id}/slots/{slot_id}`** endpoint (slot removal is not exposed).
- There is **no `GET /instances/{id}/conflicts`** — the front-end is responsible for "did this break things?".

> The `/assignments` router is **not** slot override — it manages the `subject_assignments` master grid (who teaches what to which division). Don't conflate them.

### 7.4 Row-Level Access Control — *NOT implemented*

Every route (other than `/auth/register`, `/auth/login`, `/health`) accepts any authenticated admin. There is a single `Admin` model with no roles/permissions, no HOD/Teacher/Student user classes, and no per-resource filtering. The full RBAC matrix shown in earlier versions of this doc is **aspirational** — it is collected into the `profiles` table's `department` column only as a free-text label, not an enforced scope.

### 7.5 Audit Trail — *implemented*

Every mutating request (any `POST`, `PUT`, `PATCH`, `DELETE`) writes an `audit_logs` row via the global HTTP middleware in `app/main.py`. Fields recorded:

- `method` — `POST | PUT | PATCH | DELETE` (uppercased)
- `path` — request URL path (no query string)
- `status_code` — final response status
- `admin_id` — best-effort JWT decode (`admin_id` payload field); `NULL` if no/invalid token
- `request_id` — the 8-char hex from `X-Request-ID` set on the response
- `created_at` — server timestamp

Read access: `GET /audit/` (admin-only, paginated, filterable by `method` / `admin_id` / `status_code`).

The audit write is wrapped in try/except and **never breaks the request** — if the audit insert fails, the response is still returned to the client.

### 7.6 Export Formats

All three live in `app/services/export_service.py` and share one filter layer (`get_filtered_slots`: group / faculty / year / department). See the `Generate` endpoints in §4.2 for the URL shape (`/generate/export/{pdf|csv|ical}?...`).

| Format  | Status     | Use Case                                                                                   |
|---------|------------|--------------------------------------------------------------------------------------------|
| PDF     | implemented| Printable wall charts, individual faculty timetables (ReportLab)                          |
| CSV     | implemented| Data portability, admin review in Excel                                                    |
| iCal    | implemented| Import into Google Calendar / Outlook — weekly-recurring `VEVENT`s (`RRULE FREQ=WEEKLY`, hand-written RFC 5545), anchored to `term_start` with optional `UNTIL` from `term_end` |
| JSON    | NOT exposed | The doc previously listed JSON export — there is **no `/generate/export/json` endpoint**. The `timetable_slots` are reachable via `GET /instances/{id}/slots` + filtering, which is the de-facto JSON export. |

### 7.7 Notification on Publish — *NOT implemented*

There is no notification service, no email integration, and no WebSocket / SSE push. After `POST /instances/{id}/publish`, the only way an admin or faculty member learns something happened is by polling the API. This is a planned next-phase feature; the audit row IS the "notification" today.

### 7.8 Versioning — *implemented*

Every published timetable is versioned. When `POST /instances/{id}/publish` is called for a `SELECTED` instance of a given generation, any sibling instance of the **same generation** that is currently `PUBLISHED` is automatically archived to `ARCHIVED`. The cross-generation PENDING / RUNNING history is preserved by `timetable_history` (snapshots created via `POST /history`).

- "Undo" is possible by selecting a different `SELECTED` instance and publishing it (re-archives the current one).
- There is **no `POST /history/{id}/restore`** — the only operation on history is GET (list and per-row detail).

---

## 8. Parameter Reference

Most engine behaviour is configured **outside** of `profile_parameters` — the time grid, solver timeout, and instance count are NOT keyed on the profile. The split is:

- **Time-structure values** are stored on the `CollegeSettings` singleton (id=1) via `POST /settings` / `GET /settings`. These are global — not per-profile.
- **Engine tuning** (timeout, diversity, instance count) is hardcoded in the engine OR set on the `POST /generate` request body, not stored as a `profile_parameters` row.
- **Hard-constraint behaviour** is configured via the `constraint_rules` table (per-profile) — toggling `is_active` / `parameters` — not via `profile_parameters`.
- **Soft-constraint scoring** is enabled by setting `is_active=TRUE` on the matching `constraint_rules` row whose `constraint_type` is one of `TEACHER_PREFERS_MORNING` or `MINIMIZE_STUDENT_FREE_SLOTS`.

The `profile_parameters` table (key/value store with `param_type` tag) is currently a **typed scratch area** — what the engine reads from it is narrow. The key/value data is presented in the UI but is **not wired into the solver** for most of the keys listed below.

### 8.1 Time Structure (global, on `CollegeSettings`)

| Key                          | Where it lives        | Wired? |
|------------------------------|------------------------|--------|
| `working_days`               | `CollegeSettings.working_days` (`JSON` of `["MONDAY", ...]`) | ✅ read by solver |
| `slot_duration_minutes`      | `CollegeSettings.slot_duration_minutes` (INTEGER) | ✅ read by solver |
| `slots_per_day`              | `CollegeSettings.slots_per_day` (INTEGER) | ✅ read by solver |
| `lab_slot_duration_minutes`  | not stored             | ❌ labs are detected via `subject.category == LAB` and consume 2 consecutive slots, not a configurable duration |
| `lunch_break_after_slot`     | not stored             | ❌ the engine treats all `slots_per_day` slots as schedulable |
| `lunch_break_duration_minutes`| not stored             | ❌ no model field |

### 8.2 Hard-Constraint Limits (per-profile, via `constraint_rules`)

These are not profile parameters in the key/value sense — they are constraints enabled via the `constraint_rules` table. The `registration` keeps the engine open; the `parameters` JSON column on each rule carries the options.

| Constraint type                          | Wired? | Notes |
|------------------------------------------|--------|-------|
| `FACULTY_MAX_HOURS_PER_DAY`              | ✅      | `parameters.max_hours` |
| `FACULTY_MAX_HOURS_PER_WEEK`             | ✅      | `parameters.max_hours` |
| `MAX_CONSECUTIVE_SAME_TEACHER`           | ✅      | `parameters.max_consecutive` |
| `SUBJECT_TIME_PREFERENCE`                | ✅      | `parameters.{preferred_days, preferred_slots}` |
| `TEACHER_YEAR_RESTRICTION`               | ✅      | `parameters.allowed_years` |
| `LAB_BATCH_ROTATION`                     | ✅      | splits an assignment into two batches |
| `SAME_SUBJECT_SAME_DAY`                  | ✅      | structural rule, no parameters |
| `CROSS_DEPT_DAILY_CAP`                   | ✅      | `parameters.max_per_day` (default in `CollegeSettings.config_json["max_cross_dept_per_day"]`) |
| `NO_CROSS_TIMETABLE_TEACHER/ROOM/GROUP_CONFLICT` | ✅ | structural rule, no parameters |
| `MAX_DAILY_LOAD_TEACHER` (legacy)        | ❌      | replaced by `FACULTY_MAX_HOURS_PER_DAY`; old key never reads |
| `MAX_WEEKLY_LOAD_TEACHER` (legacy)       | ❌      | replaced by `FACULTY_MAX_HOURS_PER_WEEK` |
| `MIN_PREPARATION_GAP_HOURS`              | ❌      | not enforced anywhere |
| `RESPECT_PHD_LEAVE_DAYS`                 | ❌      | not enforced; no `phd_leave_days` column on faculty |

### 8.3 Student Group Constraints (per-profile)

| Key                          | Wired? |
|------------------------------|--------|
| `max_daily_subjects`         | ❌ not read — group subjects per day are not capped |
| `allow_free_last_slot`       | ❌ not enforced |
| `min_free_slots_per_week`    | ❌ not enforced |
| `SAME_SUBJECT_SAME_DAY` (constraint) | ✅ prevents a group from having the same subject twice on the same day |

### 8.4 Room Constraints

| Key                          | Wired? |
|------------------------------|--------|
| `max_room_utilization_pct`   | ❌ not enforced — no utilisation cap in the engine |
| `prefer_fixed_home_room`     | ❌ no "home room" concept; each assignment picks a fresh room |

### 8.5 Exam / Event / IP Specific — *NOT implemented*

All keys in this category from earlier versions of the doc are aspirational:

- `min_days_between_exams`, `no_exam_on_monday`, `exam_slot_duration_minutes`, `allow_two_exams_same_day` — no exam-domain table or rule.
- `event_requires_auditorium`, `block_class_slots_for_event`, `ip_min_duration_days` — no event/IP-domain table or rule.

Today's `ProfileScope` enum only has `DEPARTMENT | YEAR | DIVISION` (see §6.1). Exam/event/IP are modelled as a regular `DEPARTMENT` profile with the relevant `profile_resources` filtered in.

### 8.6 Optimisation Tuning

| Key                          | Wired? |
|------------------------------|--------|
| `solver_timeout_seconds`     | ❌ ignored — `ORToolsSolver.max_time_seconds = 5.0` is a class constant. The router does not pass a request-side override. |
| `diversity_threshold`        | ❌ ignored — `_DIVERSITY_MIN_DISTANCE = 1` is a module constant in `scheduler.py`. |
| `instances_to_generate`      | ✅ read from `POST /generate` request body (`instances_per_generation`), not from `profile_parameters`. |

### 8.7 Soft-Constraint Scoring

Two soft scorers are implemented (`app/engine/scorer.py` — `SOFT_CONSTRAINT_REGISTRY`), and both also have CP-SAT objective builders (`app/engine/soft_objective.py` — `SOFT_OBJECTIVE_REGISTRY`):

- `TEACHER_PREFERS_MORNING` — weights morning slots over afternoon slots; `config_json.boundary_slot` (default 4), optional `faculty_id`.
- `MINIMIZE_STUDENT_FREE_SLOTS` — penalises gaps between a group's first and last scheduled slot in a day.

Other soft candidates from the registry (`AVOID_CONSECUTIVE_SAME_SUBJECT`, `MINIMIZE_TEACHER_FREE_SLOTS`, `DISTRIBUTE_SUBJECTS_EVENLY`, `BALANCE_TEACHER_LOAD`) are **catalogued** but their scorers/objective builders are not registered — enabling them in `constraint_rules` has no effect on `instance.soft_score`.

### 8.8 Calendar-date anchoring (`term_start`)

The solver is a **weekly template** — a timetable describes one repeating week, and slots carry only `day_of_week`/`slot_number` (plus a nullable `slot_date`). To let date-based rules (availability windows, holiday blackouts) participate, the profile can set a **`term_start`** parameter (`"YYYY-MM-DD"`, STRING):

- `GreedySolver._parse_term_start()` reads it once per run; `_materialize_slot_date(day)` maps each weekday to the first occurrence on/after `term_start`.
- That date is stamped on every `SlotCandidate.slot_date` and persisted on `TimetableSlot.slot_date`.
- `_check_teacher_availability` treats an availability row with no date bounds as **timeless** (applies every week); one with bounds applies only when `effective_from <= slot_date <= effective_to` (a missing bound is unbounded on that side). Without a `term_start` anchor there is no `slot_date`, so a date-bounded window is **inert** — the same rule that governs date-specific `room_blackouts`.
- This is the same anchor the iCal export already uses for its `RRULE FREQ=WEEKLY` events, so exports and the checker stay consistent.
- Future date-based rules (`HOLIDAY_CALENDAR`) will reuse this mechanism.

---

## 9. Implementation Status & Roadmap

This section reflects the **actual** state of the codebase rather than the original week-by-week plan (which dates from before OR-Tools, the constraint registry, and the audit middleware landed). For the underlying plan see `documentation/plan.md`.

### ✅ Shipped (matches the doc above)

- **Schema (22 tables)** — Alembic chain `aeaadc4f2374 → … → e9f4a2b6d8c0`; latest migration is `e9f4a2b6d8c0` (faculty availability dates nullable).
- **CRUD** — `/auth`, `/profiles`, `/subjects`, `/faculty`, `/groups`, `/rooms`, `/blackouts`, `/availability`, `/assignments`, `/settings`, `/constraints`.
- **Generation** — synchronous `POST /generate` with greedy (default) and OR-Tools CP-SAT.
- **Constraint engine** — `HARD_CONSTRAINT_REGISTRY` + `SOFT_CONSTRAINT_REGISTRY`; structural rules (double-booking, capacity, availability, blackouts, cross-timetable safety, faculty load caps, same-subject-per-day, cross-department cap) plus rule-pack rules (`SUBJECT_TIME_PREFERENCE`, `MAX_CONSECUTIVE_SAME_TEACHER`, `TEACHER_YEAR_RESTRICTION`, `LAB_BATCH_ROTATION`).
- **Soft scoring** — `TEACHER_PREFERS_MORNING`, `MINIMIZE_STUDENT_FREE_SLOTS` registered as post-hoc scorers **and** as CP-SAT objective builders (`soft_objective.py`); `AVOID_CONSECUTIVE_SAME_SUBJECT`, `MINIMIZE_TEACHER_FREE_SLOTS`, `DISTRIBUTE_SUBJECTS_EVENLY`, `BALANCE_TEACHER_LOAD` catalogued only.
- **Diversity filter** — seeded re-rolls, `_DIVERSITY_ATTEMPTS=6`, `_DIVERSITY_MIN_DISTANCE=1`.
- **Instance lifecycle** — `DRAFT → SELECTED → PUBLISHED → ARCHIVED`; publishing auto-archives the previous `PUBLISHED` sibling of the same generation.
- **Manual override** — `PATCH /instances/{instance_id}/slots/{slot_id}` sets `is_manual_override=true`, writes `override_reason`, and re-validates the new position with the full constraint checker (409 on conflict).
- **Cross-timetable safety** — `Scheduler._load_published_conflicts()` + `ConstraintChecker._check_published_conflicts()` (per-resource split sets).
- **Exports** — PDF, CSV, iCal (RFC 5545) via `/generate/export/{pdf|csv|ical}?...` with shared filter layer (`group_id`, `faculty_id`, `year`, `department`).
- **History** — `POST /history` snapshots, `GET /history`, `GET /history/{id}`; no restore endpoint.
- **Audit** — global HTTP middleware writes `audit_logs` for every `POST | PUT | PATCH | DELETE`; `GET /audit/` for admins.
- **Settings** — `college_settings` singleton auto-created on startup; `GET/PUT /settings/`.
- **Health** — `GET /health` with Postgres reachability check.
- **CSV import** — `/import/{rooms|faculty|groups|subjects}` and `/import/assignments` (dry-run + commit). All-or-nothing: any invalid row rejects the whole file (422, `inserted=0`).
- **Reset** — `POST /reset/` (FULL_YEAR archives published + clears profiles; PROFILE_SPECIFIC clears only; SEMESTER no-op) plus `GET /reset/log`; `timetable_reset_log` row written for every reset.
- **Pagination utility** — `app/utils/pagination.py` exposes `Pagination`, `pagination`, `paginate`; `GET /audit/` and several list endpoints use it.

### 🟡 Partial — *working, but with documented gaps*

- **Profile scope** — `ScopeType` enum has six values (DEPARTMENT/YEAR/DIVISION/EVENT/EXAM/CUSTOM) but only DEPARTMENT/YEAR/DIVISION have distinct solver branches; EVENT/EXAM/CUSTOM run through the same DEPARTMENT path.
- **Profile combine** — `profile_combinations` and `profile_combination_members` tables exist and `TimetableGeneration.combination_id` is a real FK, but the scheduler ignores `combination_id` and there is no `/profiles/combinations` router.
- **Manual override** — re-validated by the constraint checker, but there is still no `DELETE /instances/{id}/slots/{slot_id}` and no `GET /instances/{id}/conflicts`.
- **Export JSON** — there is no `/generate/export/json` route; consumers fetch slots via `GET /instances/{id}/slots` instead.
- **Soft scoring in CP-SAT** — soft preferences are folded into the OR-Tools objective (`soft_objective.py`), but only the two shipped rules have builders; greedy still ignores soft preferences during placement (post-hoc scoring only).
- **`SEMESTER` reset** — accepted by the schema (`ResetType` enum) but no branch handles it; falls through with the `reset_log` still written.

### 🔴 Not implemented (planned, but no code)

- **Async / Celery** — `POST /generate` is synchronous.
- **Profile combine resolve** — `POST /profiles/combinations/{id}/resolve` does not exist.
- **Profile shift** — front-end is on its own.
- **RBAC** — single-role `Admin` model; HOD/Teacher/Student users don't exist.
- **Notification on publish** — no email / WebSocket / SSE.
- **History restore** — read-only.
- **Genetic solver** — `AlgorithmType` has only `GREEDY` and `OR_TOOLS`.
- **Frontend** — backend only.

### Recommended Order for Remaining Work

1. **Async + WebSocket for generation** — biggest UX blocker today.
2. **Wire `profile_parameters` to the engine** — most of §8 is in the table but not in the solver.
3. ~~**Fold soft scoring into the CP-SAT objective**~~ — ✅ done (`soft_objective.py`; `TEACHER_PREFERS_MORNING`, `MINIMIZE_STUDENT_FREE_SLOTS`).
4. **Object-based instance variation** — replace seed-only diversity with "best / minimise teacher gaps / minimise student gaps / random".
5. **Frontend** — Next.js SPA using the API documented in §4.2.
6. **Notification service** — emails + push on publish.
7. **RBAC** — once a teacher/student app needs read scoping.
8. **Genetic solver** — only if CP-SAT still leaves real departments unsolved.



---

*End of Timetable Generator Architecture Blueprint*
