# Timetable Generator — Enterprise Architecture Blueprint
> Module of the Institutional ERP | FastAPI + MySQL | By: [Your Name]

---

## 1. What This Module Does (Scope)

The Timetable Generator is not just a class schedule maker. It is a **multi-domain scheduling engine** that produces and manages:

| Timetable Type         | Description                                               |
|------------------------|-----------------------------------------------------------|
| Class Timetable        | Subject-wise weekly schedule per division/year            |
| Faculty Timetable      | Consolidated teaching schedule per teacher                |
| Room Utilization Chart | Which rooms are occupied when                             |
| Event / Seminar Schedule | One-off or recurring special sessions                  |
| Industry Program (IP)  | Company visits, internship slots, industry lectures       |
| Exam Timetable         | Mid-sem, end-sem, viva, practicals                        |
| Lab Schedule           | Equipment-bound sessions needing specific rooms           |

All types share the same **constraint engine** and **resource pool**, ensuring zero conflicts across timetable types.

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

## 3. Database Schema (MySQL)

### 3.1 Resource Tables

```sql
-- ROOMS & SPACES
CREATE TABLE rooms (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    name            VARCHAR(100) NOT NULL,         -- e.g., "Lab 3", "Seminar Hall A"
    room_code       VARCHAR(20) UNIQUE NOT NULL,
    room_type       ENUM('CLASSROOM','LAB','SEMINAR_HALL','AUDITORIUM','OPEN_SPACE','CONFERENCE') NOT NULL,
    capacity        INT NOT NULL,
    floor           INT,
    building        VARCHAR(50),
    has_projector   BOOLEAN DEFAULT FALSE,
    has_ac          BOOLEAN DEFAULT FALSE,
    equipment_json  JSON,                           -- {"smart_board": true, "linux_machines": 30}
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ROOM BLACKOUT WINDOWS (maintenance, reserved dates)
CREATE TABLE room_blackouts (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    room_id     INT NOT NULL,
    date        DATE NOT NULL,
    slot_start  TIME,                               -- NULL = full day
    slot_end    TIME,
    reason      VARCHAR(200),
    FOREIGN KEY (room_id) REFERENCES rooms(id)
);

-- TEACHER AVAILABILITY & PREFERENCES
CREATE TABLE faculty_availability (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    faculty_id      INT NOT NULL,                   -- FK to users table
    day_of_week     TINYINT NOT NULL,               -- 0=Mon, 6=Sun
    slot_start      TIME NOT NULL,
    slot_end        TIME NOT NULL,
    availability    ENUM('AVAILABLE','PREFERRED','UNAVAILABLE') DEFAULT 'AVAILABLE',
    reason          VARCHAR(200),                   -- e.g., "PhD coursework"
    effective_from  DATE,
    effective_to    DATE
);

-- STUDENT GROUPS (divisions, batches, years)
CREATE TABLE student_groups (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    name            VARCHAR(100) NOT NULL,          -- "CS-A", "FE-2025", "TE-Batch-2"
    group_type      ENUM('DIVISION','BATCH','YEAR','DEPARTMENT','CUSTOM') NOT NULL,
    department_id   INT NOT NULL,
    year            TINYINT,                        -- 1, 2, 3, 4
    semester        TINYINT,
    strength        INT NOT NULL,                   -- student count
    parent_group_id INT,                            -- for hierarchical grouping
    FOREIGN KEY (parent_group_id) REFERENCES student_groups(id)
);
```

### 3.2 Profile & Parameter Tables

```sql
-- PROFILES (named parameter bundles)
CREATE TABLE timetable_profiles (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    name            VARCHAR(150) NOT NULL,
    description     TEXT,
    scope_type      ENUM('DEPARTMENT','YEAR','DIVISION','EVENT','EXAM','CUSTOM') NOT NULL,
    academic_year   VARCHAR(10) NOT NULL,           -- "2025-26"
    semester        TINYINT,
    department_id   INT,
    created_by      INT NOT NULL,                   -- admin user FK
    is_active       BOOLEAN DEFAULT TRUE,
    is_archived     BOOLEAN DEFAULT FALSE,
    last_used_at    DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME ON UPDATE CURRENT_TIMESTAMP
);

-- PROFILE ↔ RESOURCE MAPPINGS (which rooms, groups, teachers belong to a profile)
CREATE TABLE profile_resources (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    profile_id      INT NOT NULL,
    resource_type   ENUM('ROOM','FACULTY','STUDENT_GROUP','SUBJECT') NOT NULL,
    resource_id     INT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES timetable_profiles(id) ON DELETE CASCADE
);

-- PROFILE COMBINATIONS (profiles merged together for a run)
CREATE TABLE profile_combinations (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    name            VARCHAR(150),
    created_by      INT NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE profile_combination_members (
    combination_id  INT NOT NULL,
    profile_id      INT NOT NULL,
    weight          DECIMAL(3,2) DEFAULT 1.00,      -- relative priority if conflicts
    PRIMARY KEY (combination_id, profile_id),
    FOREIGN KEY (combination_id) REFERENCES profile_combinations(id),
    FOREIGN KEY (profile_id) REFERENCES timetable_profiles(id)
);

-- PARAMETERS (key-value store per profile, typed)
CREATE TABLE profile_parameters (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    profile_id      INT NOT NULL,
    param_key       VARCHAR(100) NOT NULL,
    param_value     TEXT NOT NULL,
    param_type      ENUM('INT','FLOAT','STRING','BOOLEAN','TIME','JSON') NOT NULL,
    description     VARCHAR(300),
    UNIQUE KEY uq_profile_param (profile_id, param_key),
    FOREIGN KEY (profile_id) REFERENCES timetable_profiles(id) ON DELETE CASCADE
);
```

#### Standard Parameter Keys (seeded defaults)

| param_key                  | type    | example value           |
|----------------------------|---------|-------------------------|
| `slot_duration_minutes`    | INT     | 60                      |
| `slots_per_day`            | INT     | 7                       |
| `working_days`             | JSON    | `["MON","TUE","WED","THU","FRI"]` |
| `lunch_break_after_slot`   | INT     | 3                       |
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
    id              INT PRIMARY KEY AUTO_INCREMENT,
    profile_id      INT,                            -- NULL = global
    constraint_type VARCHAR(100) NOT NULL,
    config_json     JSON,                           -- type-specific config
    description     VARCHAR(300),
    is_active       BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (profile_id) REFERENCES timetable_profiles(id)
);

-- SOFT CONSTRAINTS (scored, engine tries to satisfy)
CREATE TABLE soft_constraints (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    profile_id      INT,
    constraint_type VARCHAR(100) NOT NULL,
    config_json     JSON,
    weight          DECIMAL(4,2) DEFAULT 1.00,      -- higher = more important
    description     VARCHAR(300),
    is_active       BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (profile_id) REFERENCES timetable_profiles(id)
);
```

#### Built-In Constraint Types

**Hard Constraints:**
- `NO_TEACHER_DOUBLE_BOOK` — teacher cannot be in two places at same time
- `NO_ROOM_DOUBLE_BOOK` — room cannot host two sessions simultaneously
- `NO_GROUP_DOUBLE_BOOK` — student group cannot attend two sessions at once
- `ROOM_CAPACITY_SUFFICIENT` — room.capacity >= group.strength
- `ROOM_TYPE_MATCH` — lab subjects must go in lab rooms
- `TEACHER_SUBJECT_MATCH` — only assigned teachers can teach a subject
- `RESPECT_TEACHER_UNAVAILABILITY` — skip slots teacher marked UNAVAILABLE
- `RESPECT_ROOM_BLACKOUT` — skip blacked-out room/time combinations
- `EXAM_DATE_SEPARATION` — min gap between exams for same group
- `CONTIGUOUS_LAB_SLOTS` — lab must occupy consecutive slots

**Soft Constraints:**
- `TEACHER_PREFERS_MORNING` — score slots before noon higher for this teacher
- `AVOID_CONSECUTIVE_SAME_SUBJECT` — same subject not on back-to-back days
- `MINIMIZE_STUDENT_FREE_SLOTS` — reduce gaps in student schedule
- `MINIMIZE_TEACHER_FREE_SLOTS` — reduce gaps in teacher schedule
- `DISTRIBUTE_SUBJECTS_EVENLY` — spread subjects across week, not clustered
- `RESPECT_TEACHER_PREFERRED_SLOT` — soft preference windows score higher
- `PREFER_HOME_ROOM` — subject/teacher has a preferred room
- `AVOID_EARLY_MORNING_FIRST_SLOT` — configurable per teacher or group
- `BALANCE_TEACHER_LOAD` — equalize teaching hours across faculty
- `EVENT_QUIET_PERIOD` — reduce scheduling load near exam dates

### 3.4 Generation & Output Tables

```sql
-- A SINGLE GENERATION RUN (one click of "Generate")
CREATE TABLE timetable_generations (
    id                  INT PRIMARY KEY AUTO_INCREMENT,
    profile_id          INT,
    combination_id      INT,
    academic_year       VARCHAR(10) NOT NULL,
    semester            TINYINT,
    timetable_type      ENUM('CLASS','FACULTY','ROOM','EVENT','EXAM','IP','CUSTOM') NOT NULL,
    generation_status   ENUM('PENDING','RUNNING','COMPLETED','FAILED') DEFAULT 'PENDING',
    algorithm_used      VARCHAR(50),                -- 'OR_TOOLS', 'GENETIC', 'GREEDY'
    score_best_instance DECIMAL(8,4),               -- best soft-constraint score
    instances_requested INT DEFAULT 3,
    instances_produced  INT DEFAULT 0,
    run_duration_ms     INT,
    triggered_by        INT NOT NULL,               -- admin user FK
    triggered_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at        DATETIME,
    error_log           TEXT,
    FOREIGN KEY (profile_id) REFERENCES timetable_profiles(id),
    FOREIGN KEY (combination_id) REFERENCES profile_combinations(id)
);

-- ONE CANDIDATE OUTPUT FROM A GENERATION RUN
CREATE TABLE timetable_instances (
    id                  INT PRIMARY KEY AUTO_INCREMENT,
    generation_id       INT NOT NULL,
    instance_number     TINYINT NOT NULL,           -- 1, 2, 3...
    label               VARCHAR(100),               -- "Option A", "Balanced Load"
    soft_score          DECIMAL(8,4),               -- higher = better
    hard_violations     INT DEFAULT 0,              -- should always be 0
    status              ENUM('DRAFT','SELECTED','PUBLISHED','ARCHIVED') DEFAULT 'DRAFT',
    selected_by         INT,                        -- user who picked this instance
    selected_at         DATETIME,
    published_at        DATETIME,
    notes               TEXT,
    FOREIGN KEY (generation_id) REFERENCES timetable_generations(id)
);

-- INDIVIDUAL SLOTS IN AN INSTANCE (the actual timetable entries)
CREATE TABLE timetable_slots (
    id                  INT PRIMARY KEY AUTO_INCREMENT,
    instance_id         INT NOT NULL,
    slot_date           DATE,                       -- for one-off events/exams
    day_of_week         TINYINT,                    -- for recurring weekly schedule
    slot_number         TINYINT NOT NULL,
    start_time          TIME NOT NULL,
    end_time            TIME NOT NULL,
    subject_id          INT,
    faculty_id          INT,
    room_id             INT,
    student_group_id    INT,
    session_type        ENUM('LECTURE','LAB','TUTORIAL','SEMINAR','EVENT','EXAM','IP','FREE') NOT NULL,
    is_manual_override  BOOLEAN DEFAULT FALSE,
    override_reason     VARCHAR(300),
    external_speaker    VARCHAR(200),               -- for guest lectures / IP
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instance_id) REFERENCES timetable_instances(id) ON DELETE CASCADE,
    FOREIGN KEY (room_id) REFERENCES rooms(id),
    INDEX idx_instance_day (instance_id, day_of_week),
    INDEX idx_faculty_slot (faculty_id, instance_id),
    INDEX idx_group_slot (student_group_id, instance_id)
);
```

### 3.5 History & Reset Tables

```sql
-- PUBLISHED TIMETABLE ARCHIVE (immutable historical record)
CREATE TABLE timetable_history (
    id                  INT PRIMARY KEY AUTO_INCREMENT,
    original_instance_id INT NOT NULL,
    academic_year       VARCHAR(10) NOT NULL,
    semester            TINYINT,
    snapshot_json       LONGTEXT NOT NULL,          -- full denormalized snapshot
    archived_by         INT NOT NULL,
    archived_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
    archive_reason      ENUM('YEAR_RESET','SEMESTER_END','MANUAL','SUPERSEDED') NOT NULL
);

-- ANNUAL RESET LOG
CREATE TABLE timetable_reset_log (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    reset_type      ENUM('FULL_YEAR','SEMESTER','PROFILE_SPECIFIC') NOT NULL,
    academic_year   VARCHAR(10) NOT NULL,
    profiles_reset  JSON,                           -- list of profile IDs cleared
    reset_by        INT NOT NULL,
    reset_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes           TEXT
);
```

---

## 4. API Design (FastAPI)

### 4.1 Project Structure

```
timetable_service/
├── main.py
├── config.py                    # env vars, DB settings
├── database.py                  # SQLAlchemy engine + session
├── models/                      # SQLAlchemy ORM models (mirrors schema above)
│   ├── rooms.py
│   ├── profiles.py
│   ├── constraints.py
│   ├── generation.py
│   └── history.py
├── schemas/                     # Pydantic request/response models
│   ├── rooms.py
│   ├── profiles.py
│   ├── generation.py
│   └── common.py
├── routers/
│   ├── rooms.py                 # /rooms
│   ├── faculty_availability.py  # /faculty-availability
│   ├── profiles.py              # /profiles
│   ├── constraints.py           # /constraints
│   ├── generate.py              # /generate  ← core endpoint
│   ├── instances.py             # /instances
│   ├── history.py               # /history
│   └── reset.py                 # /reset
├── engine/
│   ├── scheduler.py             # Orchestrator
│   ├── constraint_checker.py    # Hard constraint validator
│   ├── scorer.py                # Soft constraint scorer
│   ├── solvers/
│   │   ├── or_tools_solver.py   # Google OR-Tools CSP solver
│   │   ├── genetic_solver.py    # Genetic algorithm fallback
│   │   └── greedy_solver.py     # Fast greedy for previews
│   └── conflict_detector.py    # Cross-timetable conflict check
├── services/
│   ├── profile_service.py       # Profile CRUD + combine logic
│   ├── generation_service.py    # Generation run lifecycle
│   ├── history_service.py       # Archive + reset operations
│   ├── export_service.py        # PDF/CSV/iCal export
│   └── notification_service.py  # Notify stakeholders on publish
├── tasks/
│   └── celery_tasks.py          # Async generation jobs (Celery + Redis)
└── utils/
    ├── pagination.py
    ├── audit.py
    └── validators.py
```

### 4.2 Core Endpoints

#### Resource Management

```
POST   /rooms                          Create room
GET    /rooms                          List rooms (with filters: type, building, min_capacity)
PUT    /rooms/{id}                     Update room
POST   /rooms/{id}/blackouts           Add blackout window
DELETE /rooms/{id}/blackouts/{bid}     Remove blackout

POST   /faculty-availability           Set teacher availability window
GET    /faculty-availability/{faculty_id}  Get teacher's full availability

GET    /student-groups                 List groups (filter by dept, year, type)
POST   /student-groups                 Create custom group
```

#### Profile Management

```
POST   /profiles                       Create new profile
GET    /profiles                       List profiles (filter: scope, year, dept, archived)
GET    /profiles/{id}                  Get profile with all params + resources
PUT    /profiles/{id}                  Update profile metadata
DELETE /profiles/{id}                  Soft delete (archive)

POST   /profiles/{id}/parameters       Set parameter(s)
GET    /profiles/{id}/parameters       Get all parameters
DELETE /profiles/{id}/parameters/{key} Remove a parameter

POST   /profiles/{id}/resources        Add resources to profile
DELETE /profiles/{id}/resources        Remove resources from profile

POST   /profiles/combine               Create a combination from multiple profiles
GET    /profiles/combinations          List saved combinations
POST   /profiles/combinations/{id}/resolve  Preview merged params (conflict report)
```

#### Constraint Management

```
GET    /constraints/types              List all built-in constraint types with docs
POST   /constraints/hard               Add hard constraint to profile or global
POST   /constraints/soft               Add soft constraint with weight
GET    /constraints?profile_id=X       Get constraints for a profile
PUT    /constraints/{id}               Update weight or config
DELETE /constraints/{id}               Remove constraint
```

#### Generation (Core)

```
POST   /generate                       Trigger a generation run (async)
  Body: {
    profile_id OR combination_id,
    timetable_type,
    academic_year,
    semester,
    instances_requested: 3,            # how many options to produce
    algorithm: "OR_TOOLS",             # or "GENETIC", "GREEDY"
    respect_existing_published: true   # check against already-published timetables
  }

GET    /generate/{run_id}/status       Poll run status (PENDING/RUNNING/COMPLETED/FAILED)
GET    /generate/{run_id}/instances    List all candidate instances from a run
GET    /generate/{run_id}/instances/{inst_id}  Full timetable data for one instance
```

#### Instance Actions

```
GET    /instances/{id}                 View full timetable
POST   /instances/{id}/select          Mark this instance as selected
POST   /instances/{id}/publish         Publish (commits to live system, notifies stakeholders)
POST   /instances/{id}/slots/{slot_id} Manual override of a slot
DELETE /instances/{id}/slots/{slot_id} Remove a slot (create FREE slot)
GET    /instances/{id}/conflicts       Re-run conflict check after manual edits
GET    /instances/{id}/diff/{other_id} Compare two instances side by side
POST   /instances/{id}/clone           Clone an instance for editing without affecting original
```

#### Export

```
GET    /instances/{id}/export/pdf      Download timetable as PDF
GET    /instances/{id}/export/csv      Download as CSV
GET    /instances/{id}/export/ical     Download as .ics calendar file
GET    /instances/{id}/export/faculty/{faculty_id}/pdf  Individual teacher timetable PDF
```

#### History & Reset

```
GET    /history                        List archived timetables (filter: year, type, dept)
GET    /history/{id}                   View archived snapshot
POST   /history/restore/{id}           Restore archived timetable as new draft instance

POST   /reset                          Trigger reset
  Body: {
    reset_type: "FULL_YEAR" | "SEMESTER" | "PROFILE_SPECIFIC",
    academic_year: "2025-26",
    profile_ids: [...],                # only for PROFILE_SPECIFIC
    archive_before_reset: true         # recommended: archive current published timetables first
  }
GET    /reset/log                      View reset history
```

---

## 5. The Scheduling Engine

### 5.1 How It Works (High Level)

```
Admin triggers POST /generate
        │
        ▼
  [1] Load Profile / Combination
      - Merge parameters (combination uses weighted merge on conflicts)
      - Load all resources: rooms, teachers, groups, subjects
      - Load all constraints: hard + soft
        │
        ▼
  [2] Cross-Timetable Conflict Loader
      - Fetch all currently PUBLISHED timetable slots
      - Block those time-room-teacher-group combinations as pre-occupied
        │
        ▼
  [3] Build CSP Problem
      - Variables: each (subject, group, teacher) tuple needing N sessions/week
      - Domains: all valid (day, slot, room) combinations
      - Constraints: hard constraints → CSP constraints
        │
        ▼
  [4] Solver Runs (multiple times for N instances)
      - Instance 1: pure optimal (best soft score)
      - Instance 2: alternate seed / different priority weighting
      - Instance 3: "spread" variant — maximize distribution
        │
        ▼
  [5] Score & Rank
      - Each instance scored against soft constraints
      - Violations counted and categorized
        │
        ▼
  [6] Return Instances to Admin
      - Admin reviews, selects, edits, or discards
```

### 5.2 Solver Strategy

**Primary: Google OR-Tools CP-SAT**
- Industry-grade constraint satisfaction solver
- Handles hundreds of variables efficiently
- Native support for time-window constraints
- Install: `pip install ortools`

```python
# Simplified example of how OR-Tools is used in the engine
from ortools.sat.python import cp_model

model = cp_model.CpModel()

# One boolean variable per (session, day, slot, room) combination
# x[s][d][t][r] = 1 if session s is assigned to day d, slot t, room r
x = {}
for session in sessions:
    for day in working_days:
        for slot in slots:
            for room in rooms:
                x[session, day, slot, room] = model.NewBoolVar(
                    f"x_{session}_{day}_{slot}_{room}"
                )

# Hard constraint: each session assigned exactly once
for session in sessions:
    model.AddExactlyOne(
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

# Soft constraint: minimize teacher gaps (add penalty variables)
# ... (weighted penalty terms added to objective)

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 30.0  # timeout
solver.parameters.num_search_workers = 4       # parallel
status = solver.Solve(model)
```

**Fallback: Greedy Algorithm**
- Used when OR-Tools times out or for quick previews
- Assigns sessions in priority order (most constrained first)
- Much faster, lower quality but always produces *something*

**Optional: Genetic Algorithm**
- For very large departments where CSP is too slow
- Population of random schedules, crossover, mutation
- Good for finding diverse instances (option 2 and 3 variety)

### 5.3 Multiple Instances Strategy

To generate meaningfully different options (not just random noise):

| Instance | Strategy                                         |
|----------|--------------------------------------------------|
| #1       | Maximize soft constraint score (best quality)    |
| #2       | Alternate objective: minimize teacher free slots |
| #3       | Alternate objective: minimize student free slots |
| #4+      | Random restarts with different seeds             |

After generation, a **diversity filter** ensures instances are sufficiently different (Hamming distance on slot assignments > threshold). If two instances are too similar, one is regenerated.

---

## 6. Profile System (Detailed)

### 6.1 Profile Scopes

```
DEPARTMENT  →  All years, all divisions, full semester
YEAR        →  Single year (e.g., only TE) — loads only TE resources
DIVISION    →  Single section/class — minimal resource set
EVENT       →  One-time event parameters (rooms, dates, special speakers)
EXAM        →  Exam-specific parameters (gap rules, no-lab-booking, etc.)
CUSTOM      →  User-defined combination of the above
```

### 6.2 Combining Profiles

The **Combine** operation creates a `profile_combination` that merges the resource pools and parameters of multiple profiles. Useful when:

- Scheduling a department event that affects multiple years
- Creating a master view after scheduling each year independently
- Running conflict detection across independent sub-profiles

**Conflict Resolution During Combine:**

When two profiles have the same `param_key` with different values:
1. **Higher-weight profile wins** (weight set in `profile_combination_members`)
2. **Restrictive-merge option** (e.g., for `max_daily_load_teacher`, take the minimum of both)
3. **Admin prompted** to resolve conflict manually via `/profiles/combinations/{id}/resolve`

### 6.3 Profile Shift

"Shifting" means changing a profile's scope mid-session. Example: admin was working on `CS-TE-2025` but now needs to switch to `CS-FE-2025`. The system:

1. Auto-saves current unsaved parameter changes
2. Loads the target profile's full state
3. Does **not** discard resources from the previous profile unless explicitly confirmed

### 6.4 Annual Reset

The reset operation is **non-destructive by default**:

1. All currently PUBLISHED instances are automatically archived to `timetable_history` (snapshot)
2. Profile metadata and constraint rules are **preserved** (they rarely change year to year)
3. The profile's `profile_resources` can optionally be cleared if "full reset" is chosen
4. `profile_parameters` are retained unless the admin checks "Reset parameters too"
5. A `timetable_reset_log` entry is created

**Why keep constraints and params?** Room capacities, teacher preferences, and slot configurations rarely change year to year. Only room assignments, teacher allocations, and subjects change.

---

## 7. Enterprise-Level Features

### 7.1 Async Generation with Job Queue

Timetable generation can take 30–90 seconds for large departments. It must never block the HTTP request.

**Stack:** Celery + Redis (Redis is already in your architecture)

```python
# routers/generate.py
@router.post("/generate")
async def trigger_generation(request: GenerationRequest, db: Session = Depends(get_db)):
    run = create_generation_run(db, request)           # creates DB record, status=PENDING
    task = run_timetable_generation.delay(run.id)      # fires Celery async task
    return {"run_id": run.id, "status": "PENDING", "poll_url": f"/generate/{run.id}/status"}

# tasks/celery_tasks.py
@celery_app.task
def run_timetable_generation(run_id: int):
    # Long-running work happens here, not in the web server
    update_run_status(run_id, "RUNNING")
    result = scheduler.execute(run_id)
    update_run_status(run_id, "COMPLETED", result)
```

Admin polls `/generate/{run_id}/status` or uses WebSocket for live progress updates.

### 7.2 Conflict Detection (Cross-Timetable)

Before confirming a generation run, the engine checks against **all currently published timetables**. This prevents:

- A teacher being in the new class schedule AND a published event schedule at the same time
- A room booked in the new timetable AND a published exam timetable

```python
# engine/conflict_detector.py
def detect_cross_timetable_conflicts(
    proposed_slots: List[SlotProposal],
    published_instance_ids: List[int],
    db: Session
) -> List[ConflictReport]:
    """
    Returns conflicts where proposed_slots collide with already-published slots.
    """
```

### 7.3 Manual Override System

After an instance is generated, the admin can make slot-level edits:

- **Drag and drop** a slot to another time (frontend sends PATCH to `/instances/{id}/slots/{slot_id}`)
- **Override is validated** by the backend (runs hard constraint check on the new slot)
- **Override is flagged** in the DB (`is_manual_override=TRUE`) for audit visibility
- **Conflict re-check** after each edit: `GET /instances/{id}/conflicts`

### 7.4 Row-Level Access Control

Timetable data is sensitive. Access follows the ERP's RBAC:

| Role            | Read                    | Write/Generate       | Publish          |
|-----------------|-------------------------|----------------------|------------------|
| College Admin   | All timetables          | All profiles         | All types        |
| HOD             | Own department only     | Department profiles  | No               |
| Class Incharge  | Own division only       | No                   | No               |
| Teacher         | Own schedule only       | Set own availability | No               |
| Student         | Own class timetable     | No                   | No               |

### 7.5 Audit Trail

Every mutation writes to the ERP's `audit_logs`:
- Profile created/modified/deleted
- Generation triggered
- Instance selected/published
- Manual slot override
- Annual reset

### 7.6 Export Formats

| Format  | Use Case                                             |
|---------|------------------------------------------------------|
| PDF     | Printable wall charts, individual faculty timetables |
| CSV     | Data portability, admin review in Excel              |
| iCal    | Import into Google Calendar, Outlook                 |
| JSON    | API consumers (student app, faculty app)             |

### 7.7 Notification on Publish

When an instance is published, the notification service fires:

- Faculty: email/push notification with their individual timetable
- HOD: summary email for department timetable
- Class Incharge: division timetable link
- Students: new timetable available banner in portal

### 7.8 Versioning

Every published timetable is **versioned**. If a new timetable is published for the same scope/semester:

- Old published instance status → `ARCHIVED`
- New instance status → `PUBLISHED`
- Old instance is preserved and viewable in history

This means "undo" is always possible: restore previous version from history.

---

## 8. Parameter Reference (Complete List)

Beyond room/teacher/hours, here are all parameters the engine supports:

**Time Structure**
- `slot_duration_minutes` — standard lecture slot length
- `lab_slot_duration_minutes` — lab sessions (usually 2× lecture)
- `slots_per_day` — total schedulable slots
- `lunch_break_after_slot` — which slot is followed by lunch break
- `lunch_break_duration_minutes`
- `working_days` — JSON array of day codes

**Teacher Constraints**
- `max_daily_load_teacher` — max slots per teacher per day
- `max_weekly_load_teacher` — max slots per week
- `max_consecutive_lectures` — no more than N in a row without break
- `min_preparation_gap_hours` — gap between different subjects for same teacher
- `respect_phd_leave_days` — skip research scholars on their academic leave

**Student Group Constraints**
- `max_daily_subjects` — unique subjects per day for a group
- `allow_free_last_slot` — whether groups can have free final slot (no early-end)
- `min_free_slots_per_week` — intentional study periods

**Room Constraints**
- `max_room_utilization_pct` — cap on how heavily a room is used (default 85%)
- `prefer_fixed_home_room` — same group always in same room if possible

**Exam-Specific**
- `min_days_between_exams` — gap between exams for same group
- `no_exam_on_monday` — soft rule
- `exam_slot_duration_minutes`
- `allow_two_exams_same_day` — boolean (for different groups)

**Event/IP Specific**
- `event_requires_auditorium` — force large events to auditorium
- `block_class_slots_for_event` — auto-block normal teaching during events
- `ip_min_duration_days` — minimum continuous days for industry program

**Optimization Tuning**
- `solver_timeout_seconds` — max time for OR-Tools solver
- `diversity_threshold` — minimum Hamming distance between instances
- `instances_to_generate` — how many candidates per run

---

## 9. Implementation Roadmap (Recommended Order)

### Phase 1 — Foundation (Week 1–2)
1. Set up FastAPI project structure
2. Create all DB tables (SQLAlchemy migrations via Alembic)
3. Build CRUD APIs for rooms, faculty_availability, student_groups
4. Build profile CRUD + parameter management APIs

### Phase 2 — Greedy Engine (Week 3)
5. Implement greedy scheduler (fast, no OR-Tools yet)
6. Implement hard constraint checker
7. Build `POST /generate` with synchronous greedy engine
8. Build instance viewer API

### Phase 3 — Real Solver (Week 4–5)
9. Install and integrate OR-Tools CP-SAT solver
10. Implement soft constraint scorer
11. Implement multi-instance generation with diversity filter
12. Add Celery async job queue

### Phase 4 — Profile System (Week 6)
13. Profile combine + conflict resolution
14. Profile shift (context switching)
15. Annual reset workflow with auto-archive

### Phase 5 — Enterprise Features (Week 7–8)
16. Manual override + conflict re-check
17. Cross-timetable conflict detection
18. Export (PDF/CSV/iCal)
19. Notification on publish
20. History and restore

---

## 10. Tech Notes for FastAPI + MySQL

```bash
# Core dependencies
pip install fastapi uvicorn sqlalchemy pymysql alembic
pip install pydantic[email]
pip install ortools          # Google OR-Tools solver
pip install celery redis     # Async task queue
pip install reportlab        # PDF export
pip install icalendar        # iCal export
```

```python
# config.py — connect to ERP's existing MySQL
DATABASE_URL = "mysql+pymysql://user:pass@localhost:3306/erp_db"

# All timetable tables live in the same MySQL DB as the rest of the ERP.
# Use table prefixes to keep them organized: tt_rooms, tt_profiles, tt_slots, etc.
```

**Integration with the main ERP (Node.js):**
The FastAPI timetable service runs as a **separate microservice** on a different port (e.g., `:8001`). The Node.js main backend calls it via HTTP when it needs timetable data. The Frontend (Next.js) can call it directly for timetable-specific pages, or route through Node.js as a proxy.

---

*End of Timetable Generator Architecture Blueprint*
