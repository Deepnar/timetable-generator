# Timetable Generator — Architecture Blueprint
> Standalone FastAPI + PostgreSQL application | Status: greedy + OR-Tools solvers working, data-driven constraint registry, soft-constraint scoring

This document is the architectural blueprint for the Timetable Generator backend. The service is a **standalone product** — it is not a module of a larger ERP. The runtime stack is **FastAPI + SQLAlchemy 2.0 + PostgreSQL 15** (via Docker). The Alembic migration history is a single linear chain:

```
aeaadc4f2374 → e47081302c4e → 0d633dc08f98 → 0f8db8a263c5
            → e5f8a91c0d4e → b7d9f2a1c3e4 → c8e1a4b6d2f7
            → d3f5a7c9e1b2 → e9f4a2b6d8c0 → b4f1c9d3e7a2
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

**Migration chain (single linear, head = `d7a3c5e9f1b2`):**

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
   → b4f1c9d3e7a2   generation variation strategy column (variationmode)
   → c2e8a4d6f0b1   subjects.requirements_json + rooms.equipment_json (generic room requirements)
   → d7a3c5e9f1b2   CUSTOM added to roomtype + sessiontype enums
```

There are **23 tables** registered with `Base.metadata` (all exported from `app/models/__init__.py`): `admins`, `faculty`, `rooms`, `student_groups`, `subjects`, `faculty_availability`, `room_blackouts`, `subject_assignments`, `college_settings`, `timetable_profiles`, `profile_resources`, `profile_parameters`, `profile_combinations`, `profile_combination_members`, `hard_constraints`, `soft_constraints`, `timetable_generations`, `timetable_instances`, `timetable_slots`, `timetable_history`, `timetable_reset_log`, `timetable_overrides`, plus `audit_logs`.

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
    -- Declarative room requirements (room_types / min_capacity / features /
    -- session_type); overrides requires_lab when set. See §5.5.
    requirements_json JSON,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- ROOMS & SPACES
CREATE TABLE rooms (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,               -- "Lab 3", "Seminar Hall A"
    room_code       VARCHAR(20) NOT NULL UNIQUE,
    room_type       roomtype NOT NULL,                   -- CLASSROOM | LAB | SEMINAR_HALL | AUDITORIUM | CUSTOM
    capacity        INTEGER NOT NULL,
    floor           INTEGER,
    building        VARCHAR(50),
    has_projector   BOOLEAN NOT NULL DEFAULT FALSE,
    has_ac          BOOLEAN NOT NULL DEFAULT FALSE,
    -- Free-form equipment/feature tags (["projector", "whiteboard", ...]) that
    -- subject room requirements match against. See §5.5.
    equipment_json  JSON,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);
-- NOTE: the doc previously listed OPEN_SPACE / CONFERENCE room_type values; the
-- RoomType enum shipped only the four college kinds, then gained a CUSTOM
-- escape hatch (migration d7a3c5e9f1b2) for exam halls / event spaces / etc.

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

-- PROFILE COMBINATIONS (profiles merged together for a run)
-- `combination_id` on the generation row selects a combination; the scheduler
-- resolves the members into one effective profile before solving (resources
-- unioned, parameters weighted, constraints merged — see §6.2).
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
| `session_type`             | STRING  | `"EXAM"` (exam mode: each assignment becomes one `SessionType.EXAM` session, see §5.4) |
| `lunch_break_after_slot`   | INT     | 3                       |
| `lunch_break_duration_minutes` | INT | 60                      |
| `max_consecutive_lectures` | INT     | 3                       |
| `max_daily_load_teacher`   | INT     | 5                       |
| `min_gap_between_exams`    | INT     | 1 (days) — legacy; superseded by the `EXAM_DATE_SEPARATION` rule's `config_json.min_days` (§5.4) |
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
| `ROOM_REQUIREMENTS_MET`           | `_room_requirements_met` (matches declared requirements vs room attributes, §5.5) |
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
| `MAX_DAILY_SUBJECTS`              | `max`, `group_id?`, `subject_id?`                           | `_max_daily_subjects` (also modelled relationally in OR-Tools) |
| `ALLOW_FREE_LAST_SLOT`            | `slots_per_day`, `group_id?`, `day_of_week?`                | `_allow_free_last_slot` (per-candidate, pruned in OR-Tools) |
| `TEACHER_YEAR_RESTRICTION`        | `faculty_id`, `allowed_years`                               | `_teacher_year_restriction`        |
| `LAB_BATCH_ROTATION`              | `group_days: {"<group_id>": [day_of_week, ...]}`            | `_lab_batch_rotation` (inert unless the `enable_lab_batches` flag is on) |
| `HOLIDAY_CALENDAR`                | `holidays: ["YYYY-MM-DD", ...]`                             | `_holiday_calendar`                |
| `EXAM_DATE_SEPARATION`            | `min_days`, `group_id?`                                     | `_exam_date_separation`            |
| `CONTIGUOUS_LAB_SLOTS`            | `block_lengths: {"<subject_id>": int}`, `default_block_length?: int` | `_contiguous_lab_slots`  |

**Soft (scorers in `app/engine/scorer.py`; CP-SAT objective builders in `app/engine/soft_objective.py`):**

| Type                              | Scorer implemented? | CP-SAT objective? | config_json keys                              |
|-----------------------------------|---------------------|-------------------|-----------------------------------------------|
| `TEACHER_PREFERS_MORNING`         | ✅ yes              | ✅ yes            | `faculty_id?`, `boundary_slot?` (default 4)   |
| `MINIMIZE_STUDENT_FREE_SLOTS`     | ✅ yes              | ✅ yes            | `{}`                                          |
| `MINIMIZE_TEACHER_FREE_SLOTS`     | ✅ yes              | ✅ yes            | `{}`                                          |
| `AVOID_CONSECUTIVE_SAME_SUBJECT`  | ❌ no               | ❌ no             | —                                             |
| `DISTRIBUTE_SUBJECTS_EVENLY`      | ❌ no               | ❌ no             | —                                             |
| `BALANCE_TEACHER_LOAD`            | ❌ no               | ❌ no             | —                                             |

**Not implemented (catalogued but with no validator / scorer):**

- `TEACHER_SUBJECT_MATCH` (hard) — implicit, because the solver only generates sessions from `subject_assignments` rows, which already bind a faculty to a subject/group.

> The catalog (`ConstraintType` enum) is the single source of truth for what the API surface accepts in `GET /constraints/types` — the endpoint derives its hard/soft lists from `HARD_CONSTRAINT_TYPES` / `SOFT_CONSTRAINT_TYPES` (defined next to the enum in `app/models/constraints.py`), so a new enum member can never drift from discovery.

> Since the registry refactor (commit `3c30e04`) the structural checks live in
> `app/engine/constraint_registry.py` too, as always-on entries (`STRUCTURAL_RULES`)
> that `ConstraintChecker.check_all` dispatches on every candidate regardless of
> the profile's `hard_constraints` rows. They remain non-negotiable and never
> per-profile; rows of a structural type are decorative.

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
    combination_id      INTEGER REFERENCES profile_combinations(id),   -- resolved into an effective profile (§6.2)
    academic_year       VARCHAR(10) NOT NULL,
    semester            SMALLINT,
    timetable_type      timetabletype NOT NULL,                       -- CLASS | FACULTY | ROOM | EVENT | EXAM | IP | CUSTOM
    generation_status   generationstatus NOT NULL DEFAULT 'PENDING',  -- PENDING | RUNNING | COMPLETED | FAILED
    algorithm_used      algorithmtype NOT NULL DEFAULT 'GREEDY',      -- native enum (not VARCHAR(50))
    variation           variationmode NOT NULL DEFAULT 'RANDOM',      -- random | best | minimize-teacher-gaps | minimize-student-gaps (§5.3)
    score_best_instance FLOAT,                                        -- best soft score; NULL when no soft rules
    instances_requested INTEGER NOT NULL DEFAULT 3,
    instances_produced  INTEGER NOT NULL DEFAULT 0,
    run_duration_ms     INTEGER,                                      -- stamped by the scheduler (sync) or the worker (async)
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
    session_type      sessiontype NOT NULL,                           -- LECTURE | LAB | TUTORIAL | SEMINAR | EVENT | EXAM | IP | FREE | CUSTOM
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

-- MID-YEAR CHANGES to a published timetable (DD-026; migration d319882e1438).
-- Base slots stay immutable; each in-term correction is a row here instead.
CREATE TABLE timetable_overrides (
    id                SERIAL PRIMARY KEY,
    instance_id       INTEGER NOT NULL REFERENCES timetable_instances(id) ON DELETE CASCADE,
    slot_id           INTEGER REFERENCES timetable_slots(id) ON DELETE CASCADE,  -- slot being changed (NULL = broad window)
    override_type     overridetype NOT NULL,        -- TEACHER_COVER | ROOM_CHANGE | SWAP | TEMP | CUSTOM
    date_from         DATE,                          -- NULL = permanent change
    date_to           DATE,                          -- set for a temporary window (TEMP)
    new_faculty_id    INTEGER REFERENCES faculty(id) ON DELETE SET NULL,
    new_room_id       INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
    swap_with_slot_id INTEGER REFERENCES timetable_slots(id) ON DELETE SET NULL, -- other leg of a SWAP
    reason            TEXT,
    created_by        INTEGER REFERENCES admins(id),
    resolved_at       TIMESTAMP,                     -- NULL = active; set when reverted/ended (kept as history)
    created_at        TIMESTAMP NOT NULL DEFAULT NOW()
);
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
├── config.py                        # pydantic-settings (DB_*, SECRET_KEY, ALGORITHM, CORS_ORIGINS)
├── database.py                      # SQLAlchemy engine + SessionLocal + Base
├── Dockerfile                       # uv-based backend image (alembic upgrade head → uvicorn)
├── docker-compose.yml               # full stack: App + Frontend + PostgreSQL + Redis (DD-018)
├── docker/
│   ├── docker-compose.yml           # backend-only dev infra (Postgres + Redis on host ports)
│   └── entrypoint.sh                # container entrypoint: migrations then uvicorn
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
│   ├── generate.py                  # GET /generate (list runs), POST /generate, GET /generate/{id}/status
│   ├── groups.py                    # /groups CRUD (incl. PUT /groups/{id})
│   ├── history.py                   # /history CRUD
│   ├── import_csv.py                # POST /import/{rooms,faculty,groups,subjects}
│   ├── instances.py                 # /instances/{generation_id}, /{instance_id}/{slots,select,publish}
│   ├── profiles.py                  # /profiles CRUD + /combine + /combinations (list/resolve)
│   ├── reset.py                     # POST /reset, GET /reset/log
│   ├── room_blackout.py             # /blackouts CRUD
│   ├── rooms.py                     # /rooms CRUD
│   ├── settings.py                  # /settings/ GET/PUT
│   └── subjects.py                  # /subjects CRUD
├── engine/
│   ├── scheduler.py                 # Scheduler.run() orchestrator
│   ├── profile_resolver.py          # ResolvedProfile + ProfileResolver (single/combination merge)
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
├── tasks/
│   └── generation.py                # run_generation Celery task + enqueue_generation()
├── worker.py                        # Celery app (celery -A app.worker:celery_app worker)
├── scripts/                         # dev/testing tools (not part of the API surface)
│   ├── seed_demo.py                 # seeds a 12-department TCET-style college (DD-020)
│   ├── battle_test.py               # runs greedy/OR-Tools generations at scale
│   ├── api_drive.py                 # drives the live HTTP API (generate/select/publish/export)
│   └── async_drive.py               # exercises the real Celery worker + Redis async path
├── tests/
│   ├── conftest.py                  # FastAPI TestClient over in-memory SQLite
│   ├── test_runner.py               # @suite / @test decorators, seed_minimal()
│   └── test_settings_and_assignments.py
└── utils/
    ├── auth.py                      # bcrypt (direct), JWT, get_current_admin
    └── pagination.py                # Pagination dataclass + paginate()
frontend/                            # Next.js 14 admin UI (DD-017, DD-019), editorial-light theme
├── package.json / tsconfig.json / next.config.mjs
├── tailwind.config.ts / postcss.config.mjs
├── .env.example                     # NEXT_PUBLIC_API_URL (backend base URL)
├── Dockerfile                       # multi-stage standalone image (bakes NEXT_PUBLIC_API_URL)
├── public/                          # static assets (favicon)
├── scripts/screenshot.mjs           # raw-CDP screenshot harness (system Chrome, no deps)
└── src/
    ├── app/                         # App Router pages (all client components)
    │   ├── layout.tsx               # root layout + AuthProvider
    │   ├── page.tsx                 # / → redirect to /dashboard
    │   ├── login/page.tsx           # /login → POST /auth/login, store JWT
    │   ├── dashboard/page.tsx       # /dashboard — counts + recent runs + quick actions
    │   ├── rooms/page.tsx           # /rooms — ResourceTable config
    │   ├── faculty/page.tsx         # /faculty — ResourceTable config
    │   ├── groups/page.tsx          # /groups — ResourceTable config
    │   └── subjects/page.tsx        # /subjects — ResourceTable config
    ├── components/
    │   ├── Navbar.tsx               # top nav + sign-out
    │   ├── ProtectedShell.tsx       # client auth guard + app shell
    │   ├── DataTable.tsx            # generic paginated table (X-Total-Count)
    │   ├── Modal.tsx                # generic modal
    │   └── ResourceTable.tsx        # config-driven CRUD table (list + filters + modals)
    └── lib/
        ├── api.ts                   # fetch client: Bearer JWT, X-Total-Count, /api/v1 base
        ├── auth.tsx                 # AuthProvider + useAuth (localStorage JWT; sync init)
        └── types.ts                 # response types mirroring the Pydantic schemas
```

The `engine/` tree intentionally does **not** have a `conflict_detector.py` or
`genetic_solver.py` — cross-timetable conflicts live in `Scheduler._load_published_conflicts()`
+ `ConstraintChecker._check_published_conflicts()`, and only two solvers exist
(greedy + OR-Tools). See §5 for the wiring. The frontend talks to the API directly
(`NEXT_PUBLIC_API_URL`, DD-019) and the browser holds the JWT in localStorage.

### 4.2 Core Endpoints

The route prefixes below match the `@router.prefix` declarations in the router files. **Every route requires a valid admin JWT except `GET /health` and the `/auth/*` endpoints** (`register`/`login`). This is enforced by one global middleware (`require_auth` in `app/main.py`) rather than a per-route dependency, so a new router/endpoint cannot accidentally be left public; the middleware runs inside the observability middleware (requests still get logged/audited) and behind CORS (rejected responses still carry CORS headers). The `get_current_admin` dependency remains on mutation endpoints that need the admin identity (`created_by`, `selected_by`, `triggered_by`, …). OpenAPI docs (`/docs`, `/openapi.json`) are also behind the gate.

The whole API is additionally mounted at `/api/v1/…` through one aggregator router in `app/main.py` (every router except `/auth`), so each route below is reachable at both the unversioned path and `/api/v1/<path>`. Unversioned routes stay live for backward compatibility; `/health` and `/auth/*` remain root-only (they are the auth-exempt paths). **Every error returns the FastAPI-default `{"detail": ...}` envelope** — HTTPExceptions keep that default shape, while validation errors (422) and unhandled errors (500) add a `request_id` via global handlers in `app/main.py` (see §7.10). All top-level list endpoints paginate through `app/utils/pagination.py` (`?skip=` / `?limit=`, plus an `X-Total-Count` response header for the unpaginated total); sub-resource lists are bounded by one parent row and stay unpaginated.

#### Resource Management

```
GET    /rooms                          List rooms (filter: room_type, min_capacity, building)
GET    /rooms/{id}                     Get one room
POST   /rooms                          Create room (accepts `room_type` incl. `CUSTOM` + `equipment_json`)
PUT    /rooms/{id}                     Update room
DELETE /rooms/{id}                     Soft delete (is_active=false)

GET    /faculty                        List faculty (filter: department)
GET    /faculty/{id}                   Get one faculty
POST   /faculty                        Create faculty (email unique)
PUT    /faculty/{id}                   Update faculty
DELETE /faculty/{id}                   Soft delete (is_active=false)

GET    /subjects                       List subjects (filter: semester, department, requires_lab)
GET    /subjects/{id}                  Get one subject
POST   /subjects                       Create subject (subject_code unique; accepts `requirements_json`)
PUT    /subjects/{id}                  Update subject
DELETE /subjects/{id}                  Soft delete (is_active=false)

GET    /groups                         List student groups (filter: year, department, group_type)
GET    /groups/{id}                    Get one group
POST   /groups                         Create group
PUT    /groups/{id}                    Update group (full CRUD parity with rooms/faculty/subjects)
DELETE /groups/{id}                    Soft delete (is_active=false)

GET    /blackouts                      List room blackouts (paginated)
GET    /blackouts/{id}                 Get one blackout
POST   /blackouts                      Create a blackout window for a room
PUT    /blackouts/{id}                 Update blackout
DELETE /blackouts/{id}                 Hard delete
                                        # NOTE: blackouts are NOT nested under /rooms/{id};
                                        # `room_id` is a field on the blackout body.

GET    /faculty_availability           List faculty availability rows (paginated)
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

GET    /settings/                      Read the college feature-flag singleton (auto-creates row id=1;
                                        # cached ~60s in Redis, busted on PUT — §7.4)
PUT    /settings/                      Update one or more flags / config_json

POST   /auth/register                  Create an admin (email + name unique); rate-limited to
                                        # 3 requests / 60s per IP → 429 (inert without Redis, §7.4)
POST   /auth/users                     Admin-only (RBAC, DD-021): create a user with a specific
                                        # role (hod/teacher/student); self-registration stays public
                                        # and defaults to admin.
POST   /auth/login                     Returns {"access_token", "token_type": "bearer"}; rate-limited
                                        # to 5 requests / 60s per IP → 429 (inert without Redis, §7.4)
GET    /auth/me                        The authenticated caller's identity + role (for the frontend
                                        # shell; RBAC role rides in the JWT and gates endpoints via

GET    /my/schedule                    Teacher self-service (DD-022 #1): the caller's OWN published
                                        # slots, resolved with subject/room/group names, plus the
                                        # published instance ids. Teacher role only; the caller's
                                        # Faculty row is found by email match (None when unmatched).
GET    /my/today                       The caller's sessions for the current weekday (day-card data).
GET    /my/export/{pdf,csv,ical}       The caller's own filtered export from the newest published
                                        # instance — a teacher pulls their iCal/PDF without knowing ids.
                                        # require_roles).

POST   /import/rooms                   Bulk import rooms via CSV (multipart file; optional `equipment_json` JSON column)
POST   /import/faculty                 Bulk import faculty via CSV
POST   /import/groups                  Bulk import student groups via CSV
POST   /import/subjects                Bulk import subjects via CSV (optional `requirements_json` JSON column)
                                        # All four are all-or-nothing: any invalid row rejects
                                        # the whole file (422, inserted=0) so the DB never ends
                                        # up holding rows the response didn't report. room_code /
                                        # email / subject_code are required and checked for
                                        # duplicates within the file AND against the DB.

GET    /health                         Liveness + DB reachability (for deploy monitors)
```

#### Profile Management

```
GET    /profiles                       List profiles (filter: academic_year, scope_type, department, is_archived; paginated)
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
                                        # members are resolved into an effective profile
                                        # automatically at generation time — see §6.2.

GET    /profiles/combinations          List every combination with its member profiles,
                                        # names, weights, and a resolution_status preview:
                                        # RESOLVABLE | INACTIVE_MEMBER | MISSING_MEMBER |
                                        # NO_MEMBERS (newest first). A status other than
                                        # RESOLVABLE means POST /generate or /resolve will
                                        # reject the combination with a 404.
POST   /profiles/combinations/{id}/resolve   Preview the merged ResolvedProfile
                                        # (combination_id, source_profile_ids, params,
                                        # resources keyed by resource type, hard/soft
                                        # constraints) that a /generate run with this
                                        # combination_id would feed to the solvers. Runs the
                                        # same ProfileResolver the scheduler uses (§6.2); a
                                        # missing / empty / archived-member combination is
                                        # a 404, matching generation-time behaviour.
                                        # NOTE: GET /profiles/combinations must be registered
                                        # BEFORE GET /profiles/{id} (Starlette path params
                                        # match any single segment, so a later literal route
                                        # is shadowed by the int-typed {id} route).
```

#### Constraint Management

```
GET    /constraints/hard               List active hard constraints (filter: profile_id; paginated)
POST   /constraints/hard               Create hard constraint
PUT    /constraints/hard/{id}          Update hard constraint
DELETE /constraints/hard/{id}          Soft delete (is_active=false)

GET    /constraints/soft               List active soft constraints (filter: profile_id; paginated)
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
POST   /generate                       Trigger a generation run (synchronous or async — §7.1)
  Body: {
    profile_id OR combination_id,                  # combination merges members into an effective profile (§6.2)
    timetable_type,
    academic_year,
    semester,
    instances_requested: 3,                         # how many options to produce
    algorithm: "OR_TOOLS" | "GREEDY",               # OR_TOOLS requires `uv add ortools`
    variation: "random",                            # instance strategy: random | best |
                                                    # minimize-teacher-gaps | minimize-student-gaps (§5.3)
    respect_existing_published: true                # always honoured: Scheduler._load_published_conflicts
  }
  Response (sync, ASYNC_GENERATION=false): 201 with the TimetableGeneration row
    (status=COMPLETED once the solver has run inline).
  Response (async, ASYNC_GENERATION=true):  202 with the row snapshotted at
    dispatch time (status=PENDING, run_id in `id`); the worker executes the run
    in the background and the client polls the status endpoint. If the broker
    is unreachable the router falls back to the synchronous path rather than
    dropping the request.
  Response when the run's resources are locked by a concurrent generation
    (§7.4): 409, and the run row is marked FAILED with error_log.

GET    /generate/{run_id}/status       Poll a run (PENDING/RUNNING/COMPLETED/FAILED)
                                        # A COMPLETED run that could not place every
                                        # session carries placement_warning (e.g.
                                        # "N session(s) could not be placed"), so
                                        # oversubscribed profiles are visible, not
                                        # silent COMPLETED.
                                        # NOTE: there is no GET /generate/{run_id}/instances
                                        # or /generate/{run_id}/instances/{inst_id} endpoint;
                                        # instance listing lives at /instances/{generation_id}
                                        # and slot detail at /instances/{instance_id}/slots.
GET    /generate                       List generation runs, newest first (skip/limit +
                                        # X-Total-Count pagination, same contract as every
                                        # other top-level list). Powers the frontend
                                        # dashboard's "recent generation runs" panel.
```

The optional admin UI (`frontend/`, §4.1) consumes this API at `/api/v1/*` through
`frontend/src/lib/api.ts` (JWT Bearer from `/auth/login`, `X-Total-Count` for pagination).
The browser calls the backend directly at `NEXT_PUBLIC_API_URL` — no proxy rewrite (DD-019).

#### Instance Actions

```
GET    /instances                          List every generated instance, newest first
                                        # (skip/limit + X-Total-Count; optional ?generation_id=
                                        # and ?status= filters; registered before /{generation_id}
                                        # so the literal list path is not shadowed).
GET    /instances/{generation_id}      List every instance for a generation run
GET    /instances/{instance_id}/slots  List every slot of an instance (ordered by day, slot)
POST   /instances/{instance_id}/select Mark an instance as SELECTED (records selected_by/_at)
POST   /instances/{instance_id}/publish  Publish (status=PUBLISHED); archives previously
                                        # PUBLISHED instances of the SAME generation; published
                                        # instances from other generations remain live and feed
                                        # cross-timetable reservations on the next run.
                                        # After the commit, publish notifications fire in a
                                        # background thread (SMTP): each faculty gets their
                                        # personal PDF, HOD/admins a full-instance summary,
                                        # each group's incharge_email their group's PDF. A no-op
                                        # when email is unconfigured; never blocks the publish
                                        # (§7.7).
PATCH  /instances/{instance_id}/slots/{slot_id}   Manual override of a slot
                                        # Sets is_manual_override=true and override_reason.
                                        # The new position is re-validated by the constraint
                                        # checker first — a conflict returns 409 and the slot
                                        # is left untouched. When only slot_number is moved,
                                        # start/end times are re-derived from the profile's
                                        # time grid so the stored row stays consistent.
POST   /instances/{instance_id}/slots/{slot_id}/revalidate
                                        # Dry-run of the checker against a proposed override
                                        # (SlotOverrideDraft — no required reason). Returns
                                        # {"slot_id", "violations": [...]} with 200 even on
                                        # conflicts, so the frontend can gate Save behind a
                                        # clean revalidate. Shares _check_candidate with the
                                        # PATCH; no slot is mutated.
                                        # NOTE: there is no DELETE /instances/{id}/slots/{slot_id}
                                        # (no "remove slot, create FREE" endpoint yet), and no
                                        # /instances/{id}/conflicts, /instances/{id}/diff/{other},
                                        # or /instances/{id}/clone. Compare is computed
                                        # client-side from the two /slots lists (§4.1 frontend).
```

#### Mid-year changes (implemented — DD-026)

Published timetables stay immutable; in-term corrections (teacher cover, room
change, swap, temporary window) are recorded as `timetable_overrides` rows and
validated before saving.

```
GET    /instances/{id}/overrides        List changes (?resolved=true|false); resolves old/new
                                        # faculty + room names, subject/group, day/slot for display.
POST   /instances/{id}/overrides        Record a change (TEACHER_COVER / ROOM_CHANGE / SWAP /
                                        # TEMP / CUSTOM). Conflict-checked against the instance's
                                        # other slots + active overrides + published reservations;
                                        # a conflict is a 409 and nothing is saved.
POST   /instances/{id}/slots/{slot_id}/swap   Swap two lectures (convenience; validates both
                                        # resulting positions before saving a SWAP override).
DELETE /instances/{id}/overrides/{oid}  Revert a change (resolved_at stamped; row kept as history).
GET    /instances/{id}/overrides/available-faculty
                                        # Candidate teachers free at a (day_of_week, slot_number):
                                        # excludes the instance's own bookings, other active
                                        # overrides, and published cross-timetable reservations.
                                        # Feeds the cover picker in the change-mode UI (§4.1).
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
    # When the slots span multiple student groups (an unfiltered whole-department
    # instance), the PDF renders one grid per group instead of cramming every
    # group into one cell — a cell that tall would exceed the page frame and
    # crash ReportLab (fixed in the scale battle test, DD-020).
```

#### History & Reset

```
GET    /history                        List archived snapshots (filter: academic_year; paginated)
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

`POST /generate` runs either **inline** (default, `ASYNC_GENERATION=false`) or through a **Celery worker** (`ASYNC_GENERATION=true`, §7.1). The run logic lives entirely in `Scheduler` (`app/engine/scheduler.py`), split into two entry points so the same code serves both modes:

- `Scheduler.create_generation(...)` — resolves the input contract and persists the `PENDING` run row (raising 404 on a missing/inactive profile or combination up front).
- `Scheduler.solve_generation(run_id)` — loads the run row, re-resolves the profile from it, solves, and flips the row to `COMPLETED` (or `FAILED` + `error_log`), stamping `run_duration_ms`. It is what the worker calls. When a completed run dropped sessions (oversubscribed profile, no matching room), the solver's `unplaced_count` is written to `placement_warning` so the API surfaces it.
- `Scheduler.run(...)` — `create_generation` + `solve_generation` in one call; the synchronous HTTP path.

Step-by-step:

1. **Resolve the input contract.** `ProfileResolver.resolve(profile_id, combination_id)` (`app/engine/profile_resolver.py`) produces a single :class:`ResolvedProfile` — for a plain run, exactly that profile's data; for a combination, the merged union of every member profile (see §6.2 for the merge semantics). The generation row stores `profile_id` (a single run) or `combination_id` (a combination) exactly as the caller asked, while the solver consumes the merged view. A missing or inactive profile / combination member is rejected up front.
2. **Cross-Timetable Conflict Loader.** `Scheduler._load_published_conflicts()` selects every `TimetableSlot` belonging to every `TimetableInstance` with `status=PUBLISHED` and builds per-resource reserved sets:
   ```
   {"faculty": {(faculty_id, day_of_week, slot_number), ...},
    "room":    {(room_id,    day_of_week, slot_number), ...},
    "group":   {(group_id,   day_of_week, slot_number), ...}}
   ```
   Splitting per resource (rather than a single 5-way tuple) means a published booking blocks the faculty, room, or group at that time slot REGARDLESS of the other dimensions. An **exam generation** passes `exempt_groups=` (the profile's own `STUDENT_GROUP` ids when the profile is in exam mode): those groups' published slots are skipped, so a branch on exams can reuse its suspended class slots while every other branch's active classes stay protected (§5.4).
3. **Build Sessions to Schedule.** From `subject_assignments` rows, expand each `(subject, faculty, group, weekly_hours, load_share)` into `weekly_hours` `SessionToSchedule` objects. Each session carries a `session_type` (derived via `subject_session_type` from the subject's declared `requirements_json.session_type`, falling back to `LAB`/`LECTURE` from `requires_lab`), the resolved room requirements (see §5.5), an `is_cross_department` flag (`group.department != subject.department`), and is dropped if the `college_settings.allow_cross_dept_subjects` flag is off and the cross-dept flag is on. In **exam mode** (§5.4) each assignment instead becomes exactly ONE `SessionType.EXAM` session.
4. **Solver Runs N times for N candidate instances.** The run row records a `variation` strategy (from the request, default `random`) that shapes the seeded re-rolls (§5.3):
   - **Instance #1: seed = `None`** (deterministic baseline) unless `variation="best"`.
   - **Instance #i (i > 0): seed = `i * 100 + attempt`**; with `variation="best"`, instance #1 is seeded too (`0 * 100 + attempt`) so a genuine optimum can be found.
   - For each attempt (up to `_DIVERSITY_ATTEMPTS = 6`): greedy shuffles `working_days` / `slot_times` / `rooms` — or reorders its search by the gap criterion for `minimize-teacher-gaps` / `minimize-student-gaps`; OR-Tools varies `solver.parameters.random_seed` and, for a gap criterion, adds a small secondary objective term (§5.2).
   - **Acceptance:** keep the first fingerprint whose Hamming distance from every already-accepted instance is ≥ `_DIVERSITY_MIN_DISTANCE = 1`; otherwise try the next seed. If all 6 attempts collide, the **last attempt** is kept (so a tiny problem still produces a result rather than a duplicate). With `variation="best"`, instead of keeping the first distinct attempt, the scheduler keeps the **highest-scoring distinct attempt** (`max` on the soft score).
5. **Score & Rank.** If `enable_soft_constraint_scoring` is on AND there is at least one active soft rule, `score_instance(slots, soft_rules, ctx)` returns a weighted-mean satisfaction in `[0, 1]` and is stored on `instance.soft_score`; the best across instances is recorded on `generation.score_best_instance`. **With no soft rules at all**, `instance.soft_score` is left unset and `generation.score_best_instance` stays `NULL`, and `variation="best"` degrades to keeping the first attempt (there is nothing to score). (For OR-Tools, the same soft rules are also folded into the CP-SAT objective — §5.2 — so the solver *pursues* them during search.)
6. **Commit & Return.** Scheduler sets `generation.status=COMPLETED`, `instances_produced`, `score_best_instance`, `completed_at`, `run_duration_ms` and `db.commit()`s. The router returns the row as the 201 response (sync) or the 202 PENDING snapshot (async). On failure `solve_generation` rolls the run back and marks the row `FAILED` with `error_log` (and `completed_at`) before re-raising — the sync router turns the re-raised exception into a 500, while the worker swallows it because the run row already records the outcome.

### 5.2 Solver Strategy

**Primary: Google OR-Tools CP-SAT** — *implemented* in `app/engine/solvers/or_tools_solver.py`.

- Industry-grade constraint satisfaction solver; select it with `algorithm="OR_TOOLS"` on `POST /generate` (greedy remains the default). Installed via `uv add ortools`.
- `ORToolsSolver` subclasses `GreedySolver` and overrides `solve()`, reusing the same session-building helpers. Constraint handling is split to match the `ConstraintChecker`:
  - **Per-candidate ("static") rules** — capacity, room requirements (§5.5), recurring blackouts, teacher availability, cross-timetable reservations, and registry rules that don't depend on committed slots (`SUBJECT_TIME_PREFERENCE`, `LAB_BATCH_ROTATION`, `HOLIDAY_CALENDAR`, `CONTIGUOUS_LAB_SLOTS`) — prune the variable domain by only creating `x[s, d, t, r]` variables that the checker accepts against an EMPTY committed set.
  - **Relational rules** — no teacher/room/group double-book, one-subject-per-group-per-day, per-faculty daily/weekly load — are added as CP-SAT constraints (`model.Add(sum(vs) <= 1)`). A block session registers its variable in the double-book buckets for *every* slot it occupies, and contributes its full length to the load buckets, so CP-SAT treats a block as a contiguous booking.
- Objective: `model.Maximize(PLACEMENT_WEIGHT * sum(x.values()) + Σ soft_terms + Σ variation_terms)` — maximise placed sessions first (`PLACEMENT_WEIGHT = 1000.0`), then optimise the active soft preferences via `app/engine/soft_objective.py` (`TEACHER_PREFERS_MORNING`, `MINIMIZE_STUDENT_FREE_SLOTS`, `MINIMIZE_TEACHER_FREE_SLOTS`; gated by `enable_soft_constraint_scoring`). Rules without a registered objective builder are skipped but still rank instances post-hoc. For a seeded instance whose run is `variation="minimize-teacher-gaps"` or `"minimize-student-gaps"`, `_build_variation_terms` additionally folds a small span term into the objective (§5.3) so the re-roll actively packs the teacher's / group's sessions instead of being a pure random seed. All secondary weights stay far below `PLACEMENT_WEIGHT`, so a soft preference or variation can only shape *which* equal-cardinality solution is returned — never trade away a placed session.
- **`EXAM_DATE_SEPARATION` is modelled as a relational CP-SAT rule** (not just a domain-pruning rule): its registry validator reads committed slots, so it cannot fire during static pruning and would otherwise only shed placements in the final pass (letting CP-SAT pack a group's exams onto one day). `_add_exam_separation` adds, per group, "at most one exam per calendar date" plus "no exams on two dates closer than `min_days`", using the materialized dates from `term_start` (inert without an anchor).
- A final pass through the full checker (with the populated committed_slots) catches committed-dependent registry rules that CP-SAT does not model. Such rules can only *drop* a placement; they cannot produce an invalid one. Two committed-dependent rules are modelled relationally instead so they don't degrade to drops: `EXAM_DATE_SEPARATION` and `MAX_DAILY_SUBJECTS`. `MAX_CONSECUTIVE_SAME_TEACHER` and `TEACHER_YEAR_RESTRICTION` rely on the final pass.
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

#### Multi-slot lab sessions (`CONTIGUOUS_LAB_SLOTS`)

Most sessions occupy exactly one slot, but a lab practical is a *block* — 2+ consecutive slots in the same room, teacher, and group. The rule's `config_json` shape is:

```json
{
  "block_lengths": {"<subject_id>": 3, "<subject_id>": 2},
  "default_block_length": 3
}
```

`block_lengths` pins specific lab subjects to a block size (JSON keys arrive as strings; int ids are matched too); `default_block_length` applies to every lab subject not listed, so one row can block an entire department's labs.

How it works end to end:

1. **Expansion** — `GreedySolver._lab_block_lengths()` reads the rule(s) off the resolved profile into a `subject_id -> length` map. `_build_sessions()` splits a governed lab assignment's `weekly_hours` into full blocks (`weekly_hours // length`) plus a single-slot remainder, so e.g. 4 hours at length 3 becomes one 3-slot block + one single session. A session carries `block_length` (default 1).
2. **Placement** — a block is a candidate that spans `slot_number .. slot_number + block_length - 1`; its `start_time`/`end_time` cover the whole span. The greedy solver only tries start slots that leave room in the day (`start + length - 1 <= slots_per_day`) and commits one `TimetableSlot` per sub-slot.
3. **Checking** — `SlotCandidate.block_length` + the `slot_numbers` range make the checker block-aware: the teacher/room/group double-book checks and the cross-timetable reservation check fire if *any* sub-slot collides; `FACULTY_MAX_HOURS_PER_DAY/WEEK` count the block's full length. Time-window rules (unavailability, room blackouts) already overlap-check the whole span. `SAME_SUBJECT_SAME_DAY` naturally allows one block per subject per group per day.
4. **Registry rules** — `SUBJECT_TIME_PREFERENCE` requires the block's *last* slot to respect `max_slot` (and its first to respect `min_slot`); `MAX_CONSECUTIVE_SAME_TEACHER` counts the block as one contiguous run; `_contiguous_lab_slots` itself is a consistency guard that a block candidate matches its configured size. `configured_block_length()` (exported from `app/engine/constraint_registry.py`) is the single resolver shared by the expansion and the validator.
5. **OR-Tools** — a block session gets variables keyed by its *start* slot (`x[si, day, start, room]`, domain-pruned by the static checker with the block's full span). It registers in the double-book buckets for every sub-slot and `block_length` times in the load buckets; the final committed-aware pass validates the whole block and expands it into sub-slots.

Known limitations: `_check_cross_dept_cap` still counts committed *slots* rather than sessions, so a committed block contributes its length to the per-day cross-dept tally; the soft CP-SAT objective builders (`TEACHER_PREFERS_MORNING`, `MINIMIZE_STUDENT_FREE_SLOTS`) key placements by a block's start slot only.

### 5.3 Multiple Instances Strategy

**Implemented (objective-based variation on top of the seeded diversity filter).** Solvers are deterministic — re-running with no seed produces the same timetable. To generate meaningfully different candidates the scheduler treats **instance #1 as a deterministic baseline** (seed = `None`) and generates each later instance with a different seed:

- **Greedy** randomises the search order of `working_days`, `slot_times`, and `rooms` via `random.Random(seed).shuffle(...)`.
- **OR-Tools** sets `solver.parameters.random_seed = self.seed` and enables `randomize_search = True`.

The diversity filter compares fingerprints. For each instance:

1. Compute `_signature(slots) = frozenset({(student_group_id, day_of_week, slot_number, subject_id), ...})`.
2. Try up to `_DIVERSITY_ATTEMPTS = 6` seeds (`seed = i * 100 + attempt`).
3. Accept an attempt only if its symmetric-difference ("Hamming-style" distance) with every already-accepted signature is at least `_DIVERSITY_MIN_DISTANCE = 1` (i.e. at least one placement must differ).
4. If no attempt clears the threshold, the **last attempt** is kept (so a tiny problem still produces a result rather than an empty or duplicated instance).

**Objective-based variation.** The `POST /generate` request body accepts a `variation` field (`app/models/generation.py::VariationMode`, persisted on the run row so the async worker reapplies it). Four strategies:

- **`"random"` (default)** — the seed-only behaviour above. Instance #1 is the deterministic baseline; instances #2+ are re-seeded re-rolls kept if they clear the Hamming gate.
- **`"best"`** — every instance is seeded (`i * 100 + attempt`, including instance #1) and the scheduler keeps the **highest-scoring distinct attempt** (soft-score `max`; ties break to the first). This is how a run can ask for "the best timetable" as instance #1 instead of the plain baseline. Without any active soft rule it degrades to keeping the first attempt, since there is nothing to score.
- **`"minimize-teacher-gaps"`** / **`"minimize-student-gaps"`** — the seeded re-rolls pursue a gap-minimising criterion so later candidates are not just random restarts:
  - **Greedy** changes its *search order*: `_build_sessions` groups each peer's (faculty / group) sessions together, and `_criterion_scan` orders the (day, slot) scan so days where the peer already teaches come first and slots beside its existing placements come first — the greedy fills around what is there instead of restarting at the earliest free slot. Every (day, slot) is still considered, so the criterion can never make a session unschedulable.
  - **OR-Tools** adds a small **span objective** (via `_build_variation_terms`, §5.2): for every (peer, day) with ≥2 placements it subtracts `last - first + 1`, pushing the solver to pack the peer's sessions into contiguous slots. The term only exists for seeded instances (seed ≠ `None`).

In every non-`"best"` strategy, instance #1 stays the deterministic baseline; only the seeded instances are reshaped. `app/engine/scorer.py` and `app/engine/soft_objective.py` both ship the gap scorers/builders under `MINIMIZE_STUDENT_FREE_SLOTS` and `MINIMIZE_TEACHER_FREE_SLOTS` (§8.7).

### 5.4 Exam scheduling (`EXAM_DATE_SEPARATION` + exam mode)

Exams reuse the weekly-template engine rather than a dedicated table. A profile whose **`session_type` parameter is `"EXAM"`** — or whose **`scope_type` is `EXAM`** (the implied form; the resolver surfaces the effective scope to the solver) — runs in *exam mode*: `GreedySolver._build_sessions` expands each `subject_assignments` row into exactly **one** `SessionType.EXAM` session (not `weekly_hours` copies), placed like any other slot but exempt from the lab-room restriction. The generation is a separate run over the examing groups' profile — so one branch/year can sit exams while the others keep their published class timetable.

Two pieces make that scenario work:

1. **`EXAM_DATE_SEPARATION`** (`_exam_date_separation` in `app/engine/constraint_registry.py`) — config `{"min_days": int, "group_id"?: int}`. Only EXAM-session candidates with a materialized `slot_date` (i.e. a `term_start` anchor, §8.8) are governed; it rejects any placement whose date is closer than `min_days` calendar days to another committed exam of the same group. Greedy enforces it inline via the growing committed set; OR-Tools models it as a relational CP-SAT rule (§5.2) so it cannot pack exams and shed them.
2. **Examing groups exempt their own class slots** — `Scheduler._load_published_conflicts(exempt_groups=...)` skips published slots whose `student_group_id` is in the exam profile's group set. Those groups have suspended their classes, so their old class slots (teacher, room, group) are reusable for exams; every other branch's rooms and faculty stay reserved, so the exam timetable can never collide with the classes still running. The same exemption is applied in the manual-override re-validation path (`app/router/instances.py::_revalidate_slot`).

Limitations: the engine is still a single-week template, so a group's exams share the one anchored week (a `min_days`-heavy schedule can leave some exams unplaced); and `EXAM_DATE_SEPARATION` is inert without `term_start`, mirroring `HOLIDAY_CALENDAR`.

### 5.5 Generic room requirements (`requirements_json` / `equipment_json`)

The engine replaces the binary `Subject.requires_lab` with a declarative requirements spec, so any "this subject needs a particular kind of room" is expressible without hardcoding lab/not-lab. The spec lives in `Subject.requirements_json` (`app/engine/resource_requirements.py`):

```json
{
    "session_type": "LAB",                       // optional; overrides the derived session type
    "room_types": ["LAB", "SEMINAR_HALL"],       // optional; absent/empty = any room type
    "min_capacity": 40,                          // optional; absent/0 = any capacity
    "features": ["projector", "ac"]              // optional; the room must satisfy every one
}
```

Matching is done by `room_matches_requirements(room, reqs) -> (ok, reason)` against room attributes:

- **`room_types`** — the room's `room_type` must be in the set.
- **`min_capacity`** — `room.capacity >= min_capacity`.
- **`features`** — each tag must appear in `Room.equipment_json`, or map onto a legacy boolean column (`"projector"` → `has_projector`, `"ac"` → `has_ac`). An unknown tag is unsatisfiable unless the room carries it in `equipment_json`.

Resolution rules (`effective_requirements` / `subject_session_type`):

- `requirements_json` wins when set (an **empty dict** means "no constraints", even with `requires_lab`).
- Otherwise `requires_lab` is shorthand for `{"room_types": ["LAB"]}`.
- `requirements_json.session_type` overrides the derived `LAB`/`LECTURE`, so a subject can produce `SEMINAR`, `TUTORIAL`, or `CUSTOM` sessions without an enum migration.

Both solvers consume it: `GreedySolver._get_rooms(session.room_requirements)` filters the profile's rooms through `room_matches_requirements`, and the `ROOM_REQUIREMENTS_MET` structural rule (renamed from `ROOM_TYPE_MATCH`) re-validates every proposed candidate in the checker. A subject whose requirements match **no** room in the profile schedules zero sessions (the greedy solver warns and returns fewer slots) rather than silently using a wrong room.

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

### 6.2 Combining Profiles — *implemented (resolution happens at generation time)*

The `profile_combinations` and `profile_combination_members` tables exist (migration `e47081302c4e`), `TimetableGeneration.combination_id` carries a foreign key to `profile_combinations.id`, and `POST /profiles/combine` creates the member rows (validating that every member profile exists, and that `weights` matches the number of members). When `POST /generate` is called with a `combination_id`, `ProfileResolver` (`app/engine/profile_resolver.py`) merges the members into one **`ResolvedProfile`** that the solvers consume exactly like a single profile. Merge semantics:

1. **Resources** — union across all members, de-duplicated by `(resource_type, resource_id)`. A room/faculty/group/subject listed by two members is attached once.
2. **Parameters** — on a `param_key` collision the member with the **highest `weight` wins**; ties break on the lower profile id so the merge is deterministic regardless of row order. The winner's value *and* `param_type` (its cast form) is what the solver reads.
3. **Hard constraints** — union of the global rows (`profile_id IS NULL`) plus every member's rows, de-duplicated by `(constraint_type, config_json)` so a rule shared by two members is not applied twice.
4. **Soft constraints** — same union, de-duplicated by `(constraint_type, config_json)` with the **highest weight kept** on collisions (a repeated preference takes the most-important weight).

The merged profile is computed **in memory per run** — no synthetic `timetable_profiles` row is created, so member edits are always reflected on the next generation and the profiles table stays clean. A generation row created from a combination records `profile_id = NULL` and `combination_id = <id>`. The slot-override re-validation (`_revalidate_slot`) re-resolves the same combination (with `require_active=False`, so an override still works if a member was archived after generation).

Combinations are discoverable and manually previewable through `GET /profiles/combinations` (list with members/weights and a `resolution_status` flag) and `POST /profiles/combinations/{id}/resolve` (returns the exact merged `ResolvedProfile` the scheduler would consume). Both live in `app/router/profiles.py` alongside `POST /profiles/combine` (§4.2).

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

### 7.1 Async Generation with Job Queue — *implemented (opt-in)*

`POST /generate` is **synchronous by default** — it blocks the HTTP request and returns a `COMPLETED` run. When the college opts in via `ASYNC_GENERATION=true` (`.env`), the router persists a `PENDING` run row and hands it to a Celery worker, returning **202 with the PENDING snapshot** immediately; the client polls `GET /generate/{run_id}/status`.

```
ASYNC_GENERATION=false:  POST /generate → router → Scheduler.run()   → 201 COMPLETED
ASYNC_GENERATION=true:   POST /generate → router → Scheduler.create_generation() → 202 PENDING
                                   └→ enqueue_generation(run_id) → Celery worker
                                          → Scheduler.solve_generation() → row COMPLETED/FAILED
                        GET /generate/{run_id}/status → poll PENDING/RUNNING/COMPLETED/FAILED
```

- **Worker.** `app/worker.py` builds the Celery app from `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`; start it with `uv run celery -A app.worker:celery_app worker --loglevel=info`. The generation task is `app/tasks/generation.py::run_generation` (`acks_late=True`, `worker_prefetch_multiplier=1` — one generation at a time, redelivery only on a worker crash). The task opens its own DB session, marks the run `RUNNING`, calls `solve_generation()`, and swallows failures because the scheduler already records them on the run row. `Scheduler.create_generation()` is split from `solve_generation()` precisely so the worker receives nothing but a `run_id` and still re-resolves everything from the run row.
- **Failure handling lives in the scheduler.** `solve_generation()` rolls back a failed run and marks it `FAILED` with `error_log` + `completed_at`; the sync router surfaces the re-raised exception as a 500, the worker swallows it.
- **Broker outage.** If `enqueue_generation()` cannot reach Redis, the router logs and falls back to solving synchronously — generation degrades to the old blocking behaviour instead of being dropped.
- **Tests.** The SQLite suite has no Redis, so the worker task is exercised by calling `run_generation(run_id)` directly (it reads `app.database.SessionLocal` at call time, so the in-memory override applies) and the async HTTP branch is exercised with Celery's `task_always_eager=True`, which runs the task inline (`app/tests/test_async_generation.py`).
- **Infra.** `docker/docker-compose.yml` now also runs a `redis:7-alpine` service on host port `6379` (the compose previously ran only Postgres).
- **Concurrency safety.** `Scheduler.solve_generation()` acquires a Redis lock keyed by the union of the run's resource ids before solving, so two concurrent runs over the same faculty/room/group cannot double-book (§7.4).
- **Not built (future):** WebSocket progress push and Celery retry/result inspection via the API.

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

**Authentication is global** (implemented): a middleware (`require_auth` in `app/main.py`) rejects every route without a valid admin JWT except `/health` and `/auth/*` (see §4.2). **Role-based access control** (DD-021): the `Admin` model carries a `role` (`admin`/`hod`/`teacher`/`student`, default `admin`), the JWT rides the role claim, `GET /auth/me` exposes it, and a `require_roles(...)` dependency 403s endpoints finer than the global gate. Admin-only `POST /auth/users` provisions non-admin roles. Teacher/student **read-scoping** (only your own schedule / your group's published timetable) is a documented follow-up once the frontend defines which views each role needs.

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

### 7.7 Email Notifications on Publish — *implemented (opt-in)*

After `POST /instances/{id}/publish` commits, `app/services/mail_service.py` fires best-effort
notifications in a **daemon thread** so SMTP latency (or an outage) never delays the publish
response. The mailer is **opt-in via .env** and degrades to a strict no-op when unconfigured —
the same posture as the Redis client (§7.9):

- **Master switch + SMTP config** — `EMAIL_ENABLED` (default `true`), `SMTP_HOST` (default empty),
  `SMTP_PORT` (587), `SMTP_USER` / `SMTP_PASSWORD` (optional login), `SMTP_FROM`. The mailer is
  active only when `EMAIL_ENABLED` **and** `SMTP_HOST` **and** `SMTP_FROM` are all set; otherwise
  `dispatch_publish_notifications` returns before spawning a thread. `.env` `SMTP_HOST`/`SMTP_FROM`
  being empty is the default "mail off" state.
- **Recipients & payloads.** One message per audience, each carrying a PDF rendered by the export
  layer (`generate_timetable_pdf`, reused directly — no new rendering code):
  - *Faculty* — every `faculty` row that has a slot in the published instance gets its **personal
    schedule PDF** (the `?faculty_id=` filter narrowed to their slots).
  - *HOD / admins* — the addresses listed in `CollegeSettings.config_json["notification_emails"]`
    get a **full-instance summary PDF** + a summary body (sessions / teaching days / faculty /
    groups). There is no HOD table in the schema; the singleton's free-form `config_json` is the
    designated place for the contact list.
  - *Class incharges* — every group with a non-null `student_groups.incharge_email` (column added
    by migration `f5a1b3c8e6d2`, nullable) gets that **group's schedule PDF**.
  - A recipient audience with no slots is skipped. Each message is plain-text + HTML (`EmailMessage`,
    stdlib `smtplib`, `STARTTLS` on port 587, optional login).
- **Never breaks the publish.** The router wraps the dispatch call in try/except, the dispatch
  itself only starts the thread, and `_deliver`/`send_publish_notifications` swallow and log per-
  recipient failures. A mail outage, a bad address, or a fully unconfigured SMTP all leave the
  publish response untouched. The SQLite suite forces `EMAIL_ENABLED=false` in `conftest.py`;
  composition is tested against a mocked delivery layer, and the transport itself is proven by
  the live-delivery tests — a real daemon-thread background run and a genuine `smtplib` dialog
  over an in-process loopback SMTP server (`app/tests/test_email_notifications.py`). Only a
  real external SMTP server (STARTTLS certs, auth, the network) is left for live verification.

Trigger points: only `POST /instances/{id}/publish`. There is no `/notifications` admin endpoint,
no per-recipient opt-out, and no retry queue yet (a failed send is logged and dropped).

### 7.8 Versioning — *implemented*

Every published timetable is versioned. When `POST /instances/{id}/publish` is called for a `SELECTED` instance of a given generation, any sibling instance of the **same generation** that is currently `PUBLISHED` is automatically archived to `ARCHIVED`. The cross-generation PENDING / RUNNING history is preserved by `timetable_history` (snapshots created via `POST /history`).

- "Undo" is possible by selecting a different `SELECTED` instance and publishing it (re-archives the current one).
- There is **no `POST /history/{id}/restore`** — the only operation on history is GET (list and per-row detail).

### 7.9 Redis-Backed Infrastructure — *implemented (opt-in)*

Beyond being the Celery broker/backend, the same Redis (`.env` `REDIS_URL`, default `redis://localhost:6379/0`; toggled off with `REDIS_ENABLED=false`) powers three app-level features through one optional client, `app/services/redis_client.py`. Every call degrades gracefully when Redis is disabled or unreachable — a missing broker means "no caching, no rate limiting, concurrent generations run unlocked", never a 500. The SQLite test suite forces `REDIS_ENABLED=false` and substitutes a dict-backed fake for the client (`app/tests/test_redis_integration.py`).

- **Generation-conflict locking.** `Scheduler.solve_generation()` acquires `timetable:lock:generate:<sorted resource ids>` (the union of the resolved profile/combination's room/faculty/group/subject ids) before solving, keyed so two concurrent runs over the same resources cannot double-book (each would otherwise compute its own empty published-reservation set). `acquire_lock` returns the lock, `False` (busy — the run is marked `FAILED` with `error_log` and the sync router returns **409**), or `None` (Redis down — run unlocked). The lock auto-expires (`DEFAULT_LOCK_TIMEOUT=600s`) and `release_lock` is a Lua compare-and-delete so a stale/re-acquired key is never clobbered.
- **Response caching.** The hot list endpoints — `GET /rooms/`, `GET /subjects/`, `GET /profiles/`, `GET /settings/` — cache their serialized JSON under `timetable:cache:<collection>:<query params>` for 60s. Cache hits restore the `X-Total-Count` header for paginated lists. Every matching write (POST/PUT/DELETE on rooms/subjects/profiles; PUT on settings) busts the whole collection prefix with a `scan_iter` + delete. Because the cache is keyed by query params, filter variations don't collide.
- **Auth rate limiting.** `POST /auth/login` (5/min) and `POST /auth/register` (3/min) run a fixed-window counter per client IP (`timetable:ratelimit:<scope>:<ip>:<window>`); exceeding the limit returns **429**. Redis-down returns `None` → always allowed, so a broker outage can never lock admins out.

### 7.10 API versioning & the JSON error envelope — *implemented*

The whole API is served under `/api/v1/` in addition to the root paths. A single `APIRouter(prefix="/api/v1")` aggregator in `app/main.py` includes every router except `/auth`, so both the unversioned and versioned paths share the same endpoints, schemas, and auth gate. The unversioned routes are kept deliberately (existing clients and `/docs` keep working); `/health` and `/auth/*` remain root-only because they are the middleware's only exempt paths.

Every error response uses the FastAPI-default `{"detail": ...}` envelope, guaranteed by two global handlers registered on the app in `app/main.py`:

- `RequestValidationError` → **422** with `{"detail": [field errors], "request_id": "…"}`.
- `Exception` → **500** with `{"detail": "Internal server error", "request_id": "…"}`.
- `HTTPException` keeps the framework's default `{"detail": "…"}` body (client-driven 4xx).

`request_id` is generated and stored on `request.state.request_id` by the observability middleware, so handlers can echo it and admins can correlate a response body with the matching log line (`X-Request-ID` header is set on every response regardless).

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
| `MAX_DAILY_SUBJECTS`                     | ✅      | `parameters.max` (relational in OR-Tools) |
| `SUBJECT_TIME_PREFERENCE`                | ✅      | `parameters.{preferred_days, preferred_slots}` |
| `TEACHER_YEAR_RESTRICTION`               | ✅      | `parameters.allowed_years` |
| `LAB_BATCH_ROTATION`                     | ✅      | splits an assignment into two batches |
| `HOLIDAY_CALENDAR`                       | ✅      | `parameters.holidays` — list of ISO dates; blocks matching `slot_date` (§8.8) |
| `CONTIGUOUS_LAB_SLOTS`                   | ✅      | `block_lengths` / `default_block_length` — runs governed lab subjects as multi-slot blocks (§5.2) |
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
| `max_daily_subjects`         | ✅ as the `MAX_DAILY_SUBJECTS` data-driven rule (config `max`) |
| `allow_free_last_slot`       | ✅ as the `ALLOW_FREE_LAST_SLOT` data-driven rule (config `slots_per_day`) |
| `min_free_slots_per_week`    | ❌ not enforced |
| `SAME_SUBJECT_SAME_DAY` (constraint) | ✅ prevents a group from having the same subject twice on the same day |

### 8.4 Room Constraints

| Key                          | Wired? |
|------------------------------|--------|
| `max_room_utilization_pct`   | ❌ not enforced — no utilisation cap in the engine |
| `prefer_fixed_home_room`     | ❌ no "home room" concept; each assignment picks a fresh room |
| `equipment_json` (on a room) | ✅ matched against a subject's `requirements_json.features` (§5.5) |
| `requirements_json` (on a subject) | ✅ the solver's room-selection + session-type source (§5.5); overrides `requires_lab` |

### 8.5 Exam / Event / IP Specific — *NOT implemented*

All keys in this category from earlier versions of the doc are aspirational:

- `min_days_between_exams`, `no_exam_on_monday`, `exam_slot_duration_minutes`, `allow_two_exams_same_day` — no exam-domain table or rule.
- `event_requires_auditorium`, `block_class_slots_for_event`, `ip_min_duration_days` — no event/IP-domain table or rule.

Today's `ProfileScope` enum only has `DEPARTMENT | YEAR | DIVISION` (see §6.1). Exam/event/IP are modelled as a regular `DEPARTMENT` profile with the relevant `profile_resources` filtered in.

### 8.6 Optimisation Tuning

| Key                          | Wired? |
|------------------------------|--------|
| `solver_timeout_seconds`     | ✅ read — a profile parameter that overrides `ORToolsSolver.max_time_seconds = 5.0`. |
| `diversity_threshold`        | ✅ read — a profile parameter that overrides `_DIVERSITY_MIN_DISTANCE = 1` (how many placements must differ for two instances to count as distinct). |
| `instances_to_generate`      | ✅ read from `POST /generate` request body (`instances_per_generation`), not from `profile_parameters`. |
| `variation`                  | ✅ read from `POST /generate` request body (`variation`), not from `profile_parameters` (§5.3). |

### 8.7 Soft-Constraint Scoring

All six catalogued soft types have both a post-hoc scorer (`app/engine/scorer.py` — `SOFT_CONSTRAINT_REGISTRY`) and a CP-SAT objective builder (`app/engine/soft_objective.py` — `SOFT_OBJECTIVE_REGISTRY`), and the greedy solver pursues them during placement via a preference-aware scan:

- `TEACHER_PREFERS_MORNING` — weights morning slots over afternoon slots; `config_json.boundary_slot` (default 4), optional `faculty_id`.
- `MINIMIZE_STUDENT_FREE_SLOTS` — penalises gaps between a group's first and last scheduled slot in a day.
- `MINIMIZE_TEACHER_FREE_SLOTS` — teacher-side mirror.
- `AVOID_CONSECUTIVE_SAME_SUBJECT` — penalises back-to-back same-subject sessions for a group (usually inert under the structural `SAME_SUBJECT_SAME_DAY` rule).
- `DISTRIBUTE_SUBJECTS_EVENLY` — rewards spreading a subject's sessions across distinct weekdays.
- `BALANCE_TEACHER_LOAD` — rewards an even spread of each teacher's load across days.

The two gap rules double as the objective terms behind the `variation="minimize-teacher-gaps"` / `"minimize-student-gaps"` strategies (§5.3): a run with those variations folds the matching span term into the OR-Tools objective even when the profile defines no such soft rule.

### 8.8 Calendar-date anchoring (`term_start`)

The solver is a **weekly template** — a timetable describes one repeating week, and slots carry only `day_of_week`/`slot_number` (plus a nullable `slot_date`). To let date-based rules (availability windows, holiday blackouts) participate, the profile can set a **`term_start`** parameter (`"YYYY-MM-DD"`, STRING):

- `GreedySolver._parse_term_start()` reads it once per run; `_materialize_slot_date(day)` maps each weekday to the first occurrence on/after `term_start`.
- That date is stamped on every `SlotCandidate.slot_date` and persisted on `TimetableSlot.slot_date`.
- `_check_teacher_availability` treats an availability row with no date bounds as **timeless** (applies every week); one with bounds applies only when `effective_from <= slot_date <= effective_to` (a missing bound is unbounded on that side). Without a `term_start` anchor there is no `slot_date`, so a date-bounded window is **inert** — the same rule that governs date-specific `room_blackouts`.
- This is the same anchor the iCal export already uses for its `RRULE FREQ=WEEKLY` events, so exports and the checker stay consistent.
- `HOLIDAY_CALENDAR` (registry rule) reuses this mechanism: its validator (`_holiday_calendar` in `app/engine/constraint_registry.py`) refuses any candidate whose materialized `slot_date` appears in `config_json.holidays` (`["YYYY-MM-DD", ...]`), and is a **no-op** when the slot carries no date — so a profile without `term_start` cannot accidentally blank out every week.
- `EXAM_DATE_SEPARATION` (registry rule, §5.4) uses the same dates: it rejects an exam candidate placed closer than `min_days` to another exam of the same group, and is a no-op when the slot carries no date.

### 8.9 Notification config (env + college singleton)

Publish notifications (§7.7) are switched by `.env` flags on `app/config.py` and one college-level
value:

| Key | Where it lives | Wired? |
|-----|----------------|--------|
| `EMAIL_ENABLED` | `.env` (default `true`) | ✅ master switch; `false` → mailer is a no-op |
| `SMTP_HOST` | `.env` (default empty) | ✅ empty → mailer is a no-op (the default "mail off" state) |
| `SMTP_PORT` | `.env` (default `587`) | ✅ `STARTTLS` used on 587 |
| `SMTP_USER` / `SMTP_PASSWORD` | `.env` (default empty) | ✅ optional login; empty → no AUTH |
| `SMTP_FROM` | `.env` (default empty) | ✅ `From:` header; empty → mailer is a no-op |
| `config_json["notification_emails"]` | `CollegeSettings` (via `PUT /settings/`) | ✅ list of HOD/admin addresses receiving the publish summary (§7.7) |
| `student_groups.incharge_email` | per-group column (migration `f5a1b3c8e6d2`) | ✅ class incharge contact; nullable, set via `POST /groups` |

---

## 9. Implementation Status & Roadmap

This section reflects the **actual** state of the codebase rather than the original week-by-week plan (which dates from before OR-Tools, the constraint registry, and the audit middleware landed). For the underlying plan see `documentation/plan.md`.

### ✅ Shipped (matches the doc above)

- **Schema (23 tables)** — Alembic chain `aeaadc4f2374 → … → d7a3c5e9f1b2 → f5a1b3c8e6d2`; latest migration is `d319882e1438` (`timetable_overrides`, the mid-year change layer).
- **CRUD** — `/auth`, `/profiles`, `/subjects`, `/faculty`, `/groups`, `/rooms`, `/blackouts`, `/availability`, `/assignments`, `/settings`, `/constraints`.
- **Generation** — `POST /generate` with greedy (default) and OR-Tools CP-SAT, running synchronously by default or through a Celery worker when `ASYNC_GENERATION=true` (§7.1). `Scheduler` is split into `create_generation()` (PENDING row + run_id) and `solve_generation()` (worker entry point); failures flip the run to `FAILED` with `error_log`.
- **Profile combination resolution** — `POST /generate` accepts `combination_id`; `ProfileResolver` (`app/engine/profile_resolver.py`) merges member resources / parameters / hard+soft constraints into one effective profile before solving (§6.2). `GET /profiles/combinations` lists combinations with member names/weights and a `resolution_status` preview, and `POST /profiles/combinations/{id}/resolve` returns the merged `ResolvedProfile` for manual preview (§4.2).
- **Constraint engine** — `HARD_CONSTRAINT_REGISTRY` + `SOFT_CONSTRAINT_REGISTRY`; structural rules (double-booking, capacity, availability, blackouts, cross-timetable safety, faculty load caps, same-subject-per-day, cross-department cap) plus rule-pack rules (`SUBJECT_TIME_PREFERENCE`, `MAX_CONSECUTIVE_SAME_TEACHER`, `MAX_DAILY_SUBJECTS`, `TEACHER_YEAR_RESTRICTION`, `LAB_BATCH_ROTATION`, `HOLIDAY_CALENDAR`, `EXAM_DATE_SEPARATION`). All six soft types (`TEACHER_PREFERS_MORNING`, `AVOID_CONSECUTIVE_SAME_SUBJECT`, `MINIMIZE_STUDENT_FREE_SLOTS`, `MINIMIZE_TEACHER_FREE_SLOTS`, `DISTRIBUTE_SUBJECTS_EVENLY`, `BALANCE_TEACHER_LOAD`) ship scorers + CP-SAT objective builders, and the greedy solver pursues them during placement via a preference-aware scan.
- **Exam scheduling** — `session_type: EXAM` profile mode turns each assignment into one `SessionType.EXAM` session; `EXAM_DATE_SEPARATION` spaces a group's exams by `min_days` (relational CP-SAT rule in OR-Tools); the published-conflict loader exempts the examing groups' own class slots so one branch can exam while others teach (§5.4).
- **Multi-slot lab sessions** — `CONTIGUOUS_LAB_SLOTS` registry rule: `_build_sessions` expands governed lab subjects into contiguous blocks, the checker double-booking/load/reservation checks are block-aware via `SlotCandidate.block_length`, and OR-Tools models blocks per start slot with per-sub-slot exclusivity (§5.2).
- **Soft scoring** — `TEACHER_PREFERS_MORNING`, `MINIMIZE_STUDENT_FREE_SLOTS`, `MINIMIZE_TEACHER_FREE_SLOTS` registered as post-hoc scorers **and** as CP-SAT objective builders (`soft_objective.py`); `AVOID_CONSECUTIVE_SAME_SUBJECT`, `DISTRIBUTE_SUBJECTS_EVENLY`, `BALANCE_TEACHER_LOAD` catalogued only.
- **Diversity filter + objective-based variation** — seeded re-rolls (`_DIVERSITY_ATTEMPTS=6`, `_DIVERSITY_MIN_DISTANCE=1`), with a per-run `variation` strategy (`random` / `best` / `minimize-teacher-gaps` / `minimize-student-gaps`, §5.3).
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
- **Pagination utility** — `app/utils/pagination.py` exposes `Pagination`, `pagination`, `paginate`; every top-level list endpoint (`rooms`, `faculty`, `groups`, `subjects`, `assignments`, `audit`, `profiles`, `constraints/hard`, `constraints/soft`, `history`, `blackouts`, `faculty_availability`, `generate`) paginates with `?skip=`/`?limit=` and an `X-Total-Count` header (§4.2).
- **Redis integration** — optional client (`app/services/redis_client.py`) with graceful degradation: generation-conflict locking (`409` on a busy run), response caching for rooms/subjects/profiles/settings (busted on write), and IP rate limiting on `/auth/login` + `/auth/register` (`429`). Gated by `REDIS_ENABLED` (§7.9).
- **Email notifications on publish** — opt-in SMTP mailer (`app/services/mail_service.py`): on `POST /instances/{id}/publish`, faculty get their personal PDF, HOD/admins (`config_json["notification_emails"]`) the full-instance summary, and class incharges (`student_groups.incharge_email`, migration `f5a1b3c8e6d2`) their group's PDF. Delivery is a non-blocking daemon thread; unconfigured SMTP (`EMAIL_ENABLED=false` or empty `SMTP_HOST`/`SMTP_FROM`) is a strict no-op and mail failures never fail the publish (§7.7, §8.9).
- **API versioning + JSON error envelope** — the whole API is mounted at `/api/v1/` via one aggregator router (unversioned paths stay live); global handlers guarantee the `{"detail": ...}` envelope with `request_id` on 422/500 (§7.10).
- **Frontend** — `frontend/` is a Next.js 14 App Router + TypeScript + Tailwind admin UI (DD-017): login (JWT in localStorage), dashboard (resource counts from `X-Total-Count` + recent runs from `GET /generate` + quick actions), and CRUD tables for rooms/faculty/groups/subjects driven by a shared `ResourcePage` with **drill-down navigation** (category tiles, facet rail, breadcrumbs, URL state). The browser calls `/api/v1/*` directly at `NEXT_PUBLIC_API_URL` (DD-019). Dockerized via `frontend/Dockerfile` (standalone Next image). Styled in the **editorial-light** theme (warm canvas, white shadow-separated cards, serif display headings, charcoal accents, ink sidebar); a raw-CDP screenshot harness (`frontend/scripts/screenshot.mjs`) drives a real login + per-page capture for visual verification. The scheduling read path ships: `/generate` (profile picker + run cards with 2s status polling), `/instances` (all-instances list), `/instances/[id]` (the **TimetableGrid**: pure-CSS day×slot grid with sticky headers, subject-hued color coding, row-spanning blocks, faculty/room/group per cell, PDF/CSV/iCal/Select/Publish/Compare actions), and `/exports`. Phase 4 (editing & comparison) adds `/instances/compare` (two scroll-synced TimetableGrids with per-cell add/remove/change markers, a summary bar, and a click-to-scroll diff list — the diff is computed client-side from the two `/slots` lists, no backend compare endpoint), the **slot override UI** (clicking a DRAFT/SELECTED cell opens an anchored editor with day/slot/room/faculty selects; a debounced `POST …/slots/{id}/revalidate` dry-run gates Save), and the **assignment grid** `/assignments` (a subject × group matrix scoped by department + semester: faculty avatar + weekly-hours badge per cell, anchored cell editor over the `subject_assignments` CRUD, coverage chips, and a least-loaded-faculty Auto-fill for unassigned cells). The drill-down and grid work surfaced and fixed two real backend bugs: CORS never exposed `X-Total-Count` to the browser, and there was no all-instances list endpoint.
- **Full-stack Dockerization** — top-level `docker-compose.yml` runs App + Frontend + PostgreSQL + Redis in one command (DD-018); backend `Dockerfile` uses the official uv image and runs `alembic upgrade head` before uvicorn. `docker/docker-compose.yml` stays the backend-only dev infra.
- **Scale battle test** — `scripts/seed_demo.py` + `scripts/battle_test.py` + `scripts/api_drive.py` + `scripts/async_drive.py` verify the engine against a 12-department TCET-style college (576 subjects / 345 faculty / 192 groups / 204 rooms / 1152 assignments). Greedy places all 288 sessions of a whole-department profile in ~4.3s (all 12 departments); OR-Tools places all 36 sessions of a per-semester profile; the real Celery worker + Redis async path, the generation lock, and cross-timetable safety were all exercised live. Surfaced and fixed two scale bugs (multi-group PDF `LayoutError`; missing `run_duration_ms` on `GenerationResponse`) — see DD-020.
- **Backend saleability hardening** — the follow-up pass closed the remaining loose ends: all six soft constraint types ship scorers + CP-SAT builders and greedy pursues them during placement; OR-Tools models `MAX_CONSECUTIVE_SAME_TEACHER`, `MAX_DAILY_SUBJECTS`, and `EXAM_DATE_SEPARATION` relationally; `scope_type=EXAM` implies exam mode; `solver_timeout_seconds` / `diversity_threshold` profile params are read; `ALLOW_FREE_LAST_SLOT` and `MAX_DAILY_SUBJECTS` are new data-driven rules; `placement_warning` and honest `hard_violations` surface on runs/instances; and RBAC (roles + `require_roles` + `/auth/me` + `/auth/users`) landed.
- **Full-features-at-scale verification** — `scripts/full_stack_test.py` re-verifies every capability at whole-department scale (soft pursuit, new rules, OR-Tools relational + greedy fallback, honesty fields, RBAC, conflict audit, real Celery async path). Surfaced and fixed two more real bugs: OR-Tools returned **0 slots** on a big relational-rule profile when CP-SAT exceeded its budget before a first solution (now falls back to greedy — a whole-dept run returns 288/288 instead of empty), and a duplicate admin name returned **500** (now **409**).

### 🟡 Partial — *working, but with documented gaps*

- **Profile scope** — `ScopeType` values: DEPARTMENT/YEAR/DIVISION share the class-timetable engine; **`EXAM` scope now implies exam mode** (`session_type` param no longer required, §5.4); **EVENT/CUSTOM are escape hatches** that run the same engine with custom data (e.g. an event profile whose "subjects" are the sessions to place in "rooms") rather than dedicated solver branches.
- **Manual override** — re-validated by the constraint checker, but there is still no `DELETE /instances/{id}/slots/{slot_id}` and no `GET /instances/{id}/conflicts`.
- **Export JSON** — there is no `/generate/export/json` route; consumers fetch slots via `GET /instances/{id}/slots` instead.
- **Soft scoring in CP-SAT** — soft preferences are folded into the OR-Tools objective (`soft_objective.py`) and the greedy solver now also pursues them during placement (preference-aware scan); all six catalogued soft types have both a post-hoc scorer and a CP-SAT builder.
- **`SEMESTER` reset** — accepted by the schema (`ResetType` enum) but no branch handles it; falls through with the `reset_log` still written.

### 🔴 Not implemented (planned, but no code)

- **Async / Celery generation** — opt-in via `ASYNC_GENERATION=true`; `POST /generate` returns 202 PENDING and a worker runs `solve_generation()`, flipping the run to COMPLETED/FAILED with `error_log` (§7.1). *Remaining:* WebSocket progress push, Celery result inspection via the API.
- **Profile shift** — front-end is on its own.
- **RBAC read-scoping** — roles exist (DD-021: admin/hod/teacher/student, JWT role claim, `require_roles`, `/auth/me`, admin-only `/auth/users`), but teacher/student reads are not yet filtered to their own schedule/group. (HOD *mail* recipients are still configured via `config_json["notification_emails"]`, §7.7 — re-pointing the mailer at HOD-role accounts is a DD-001 follow-up.)
- **History restore** — read-only.
- **Genetic solver** — `AlgorithmType` has only `GREEDY` and `OR_TOOLS`.
- **Frontend depth** — shipped: Auth + Dashboard + Resource CRUD (with drill-down navigation), Generation trigger, Instances list, the TimetableGrid viewer with exports, **compare mode**, the **slot override editor**, the **assignment grid**, the **profile/constraint builder**, the **mid-year change mode** on published timetables, and the **teacher portal** (`/my-schedule` — Today card + weekly grid + own exports, with role-based login redirect) (§4.1). Remaining (plan.md Phase 4): the student portal and the date-resolution day layer (DD-022 #2/#3).

### Recommended Order for Remaining Work

1. **WebSocket progress push for generation** — the async worker (§7.1) already exposes PENDING/RUNNING/COMPLETED; push state changes instead of polling.
2. **Wire `profile_parameters` to the engine** — most of §8 is in the table but not in the solver.
3. ~~**Fold soft scoring into the CP-SAT objective**~~ — ✅ done (`soft_objective.py`; `TEACHER_PREFERS_MORNING`, `MINIMIZE_STUDENT_FREE_SLOTS`, `MINIMIZE_TEACHER_FREE_SLOTS`).
4. ~~**Object-based instance variation**~~ — ✅ done (`variation` field on `POST /generate`; `random` / `best` / `minimize-teacher-gaps` / `minimize-student-gaps`, §5.3).
5. ~~**Frontend (first slice)**~~ — ✅ done (Auth + Dashboard + Resource CRUD, §4.1). Remaining UI: the student portal (plan.md Phase 4).
6. ~~**Notification service**~~ — ✅ done (email on publish, §7.7; WebSocket / SSE push remains open).
7. ~~**RBAC**~~ — ✅ roles exist (DD-021); the remaining teacher/student read-scoping is listed under 🟡 Partial.
8. **Genetic solver** — only if CP-SAT still leaves real departments unsolved.



---

*End of Timetable Generator Architecture Blueprint*
