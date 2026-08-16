# Progress Tracker — Timetable Generator

> ## 🔴 Read `documentation/system-audit-and-plan.md` before trusting anything below
>
> An independent audit (15 Aug 2026, **DD-031**) found the engine is solving the wrong problem.
> Features marked ✅ Completed below are *implemented*, but several are **implemented against a
> model that cannot express a real college timetable**. In particular "parallel per-batch
> practicals (DD-030)" is shipped and does not match reality: TCET's real lab window runs
> **different subjects** for different batches simultaneously (52 of 78 real windows), which the
> current model cannot represent.
>
> Measured on the live DB: 26/36 divisions drop sessions · **245/245** lecture pairs split across
> rooms · 175 sessions in the BREAK row · 163 Saturday sessions · 35/63 lab pairs leave a batch
> with no practical · OR-Tools produces **zero practicals**. Meanwhile 216/216 tests pass —
> the suite tests plumbing on toy data.
>
> The work queue is `documentation/HANDOFF.md`.

This document provides a living status of every feature, table, and improvement discussed in the architecture blueprint (`documentation/timetable-generator-architecture.md`) and the session notes (`rough_plan.md`). 

**Current State:** greedy and OR-Tools (CP-SAT) solvers working, data-driven constraint registry, soft-constraint scoring, objective-based instance variation (best / minimize gaps), opt-in async generation (Celery/Redis), a Next.js admin frontend (Auth + Dashboard + Resource CRUD), full-stack Dockerization, **parallel per-batch practicals (DD-030)** — a lab splits into B batches placed at the same time in distinct rooms (FE 3, SE+ 2), max-one-lab-per-day rule — and a **real-data import pipeline** (`scripts/import_tcet.py` reads `info/import/*.json`; 46 classes generated + published from real TCET data).

> ⚠️ **The old `scripts/seed_demo.py` is a fabricated demo** (invented departments
> ELX/ELEC/CHEM/INST/CSBS, uniform FE-under-every-department, 176 faculty/dept, strength
> 60, made-up FE scheme). The real college structure comes from `info/` (scraped site)
> via `scripts/import_tcet.py`; see `documentation/real-data-rollout-plan.md`.
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

## 🧪 Parallel practicals & real-data import (DD-030, 14 Aug 2026)

- [x] **Parallel per-batch practicals** — a lab block expands into B sibling sessions
  (FE → 3 batches, SE+ → 2 lab groups, `lab_batches` param override) placed atomically
  at the same (day, slot) in distinct rooms with distinct faculty (`_place_parallel_group`
  / `_parallel_rooms` in the greedy solver). `timetable_slots.batch_number` +
  `subject_assignments.batch_number` encode the batch; `MAX_ONE_LAB_PER_DAY` rule added;
  exports show `Batch B{n}`. Greedy-only (OR-Tools keeps the whole-division model).
  7 new tests (`test_parallel_labs.py`), 216 total.
- [x] **Real-data import pipeline** — `scripts/import_tcet.py` seeds Postgres from
  `info/import/*.json` + `info/import/synthetic_branches.json`, scoped to the 6 branches
  with published grids (COMP/IT/EXTC/E&CS/MECH/CIVIL). **Branch-bound faculty pools**
  (~40/branch; COMP uses the real roster), per-branch room pools, real scheme hours
  (lecture 3 / tutorial 1 / lab 2h / activity 2), retire-own-published-on-republish so a
  regeneration is not blocked by its own stale morning slots. Full-college generation:
  **36/36 classes published, morning-filled, ~1,220 slots, ~90 unplaced** (down from 228;
  MECH-SE 53 → 6). The rest of the college (MBA/MCA/BCA/AI&ML/AI&DS/IoT/CSE-IoT/CS&E/MME/
  FE) has no published-grid data and is deliberately excluded.
- [x] **Grid/legend fixes** in `scripts/generate_tcet_import.py` — correct per-slot times,
  and a legend parser that handles `CODE (INIT = Name)` and `CODE (INIT / INIT)` (was
  only matching `CODE = Name`, so almost every subject code was lost).
- [x] **Per-branch synthetic dataset** — `scripts/build_synthetic_branches.py` →
  `info/import/synthetic_branches.json` (40 branch-bound faculty per branch, 16
  classrooms + 8 labs + real grid rooms per branch).
- [x] **Frontend** — TimetableGrid stacks parallel batches in one cell with `B{n}` badges,
  online badges, wider/taller grid so stacked labs scroll instead of overlapping; the
  generate page has a first-run guide.

## 🔧 Phase 0 — Stop the bleeding (15 Aug 2026, DD-032/DD-033)

First tranche of the DD-031 rebuild plan. Security + correctness only; no model changes yet.

- [x] **Privilege escalation closed (B-CRIT-1/B-HIGH-2)** — `overrides.py` and `notifications.py`
  mounted with no role guard; any self-registered STUDENT could rewrite a published timetable via
  `POST /instances/{id}/overrides` or `.../slots/{id}/swap`. `overrides.py` is now
  admin/hod-gated; `notifications.py` is gated to all four roles (it is recipient-scoped
  self-service, so restricting it would have broken the portal bell — see DD-033).
- [x] **Mutation-sweep regression test** — `test_security.py` enumerates every mutating route in
  the OpenAPI schema and asserts a STUDENT token is 403 on all but the public auth and
  recipient-scoped notification paths. A new unguarded router fails the suite the same day.
- [x] **B1** — `Callable` is now imported in `greedy_solver.py` (was referenced in a local
  annotation without the import; a refactor would have NameError'd).
- [x] **B2** — `CROSS_DEPT_DAILY_CAP` counted *all* of a faculty's sessions that day; it now
  counts only cross-department ones (recomputed from subject/group departments, since committed
  slots don't persist the flag).
- [x] **A3 dedup** — unique expression index
  `(subject_id, group_id, COALESCE(batch_number,0), COALESCE(period_number,0))` on
  `subject_assignments`; migration `e6a1b7c3d9f2` de-duplicated the 37 offending pairs (540 → 495
  rows). `POST/PUT /assignments` return 409 on a duplicate instead of 500. Model + migration in
  sync (no `alembic check` drift on this table).

## 🗓️ Phase 1 — Make the grid real (15 Aug 2026, A2 + A5)

Second tranche of the DD-031 rebuild plan: the time grid and the room domain.

- [x] **Break is a numbered slot (`break_slots`)** — per-profile JSON param sourced from the
  division's published BREAK cells (modal slot across teaching days, matching the audit's
  measured 4×45/5×51/3×41/6×28). `_build_slot_times` reads `slot_times` verbatim from
  `grids.json`; the synthetic `day_start_time`/`slot_duration_minutes`/`lunch_*` arithmetic is
  now only the fallback for colleges without a grid. New structural validator
  `NO_TEACHING_IN_BREAK_SLOT` (also rejects a block spanning a break). Migration `f7b2c8d4e1a3`.
- [x] **`saturday_policy`** (`NONE|ACTIVITY_ONLY|FULL`) — `NONE` strips Saturday from working
  days; `ACTIVITY_ONLY` admits it only for activity sessions; `FULL` is a normal day. Working
  days are now derived per division from the days that actually carry teaching cells.
- [x] **Home rooms (`student_groups.home_room_id` / `home_room_secondary_id`)** — imported from
  the published venue. `_get_rooms` **hard-restricts** non-lab sessions to these rooms (a
  restriction, not a sort order); labs and venue-less groups keep the general pool.
- [x] **`ROOM_STABILITY` soft scorer** — fraction of a division's non-lab sessions in its venue;
  stamped on every imported profile.
- [x] **Importer fixes surfaced by the unique index** — grid-duplicate assignment rows are
  skipped (UHV appearing as both LECTURE and TUTORIAL), and auto-fill sees grid rows before
  inventing load (flush before its `has` check).

**Measured exit metrics (11 COMP divisions, published):**

| Metric | Before (audit) | After |
|---|---|---|
| sessions in a break slot | 175 | **0** |
| Saturday sessions | 163 | **0** |
| lecture room stability | 0% | **100%** |
| slot times vs `grids.json` | 18:30 end | **exact (0 mismatches)** |
| unplaced sessions | 26/36 divisions | still present (honest — removed the fake Saturday/break capacity; zero-unplaced is Phase 4) |

## 🧪 Phase 2 — Model the lab window (16 Aug 2026, A1)

Third tranche of the DD-031 rebuild plan: the lab window becomes the atomic scheduling unit.

- [x] **`period_number` re-scoped to the GROUP** — a window is `(group_id, period_number)`; its
  members are `(batch_number, subject_id, faculty_id)` rows sharing that period. The importer
  groups lab cells by (day, contiguous-slot-run) and numbers windows per group, so CG's D1D2 and
  IIS's D3D4 in the same window share one period. `subject_assignments.block_length` carries the
  window's slot span (1 for most, 2 for BE's merged block).
- [x] **Window construction in the solver** — `_build_sessions` groups batched rows by
  `(group_id, period_number)` into a base session with `window_members`; `_expand_lab_batches`
  emits one session per batch, each with its own subject. `timetable_slots.window_key` stamps
  every batch slot (migration `a1b3c5d7e9f1`).
- [x] **Siblings match window identity, not subject** — `_is_parallel_sibling` compares
  `window_key`, so different-subject members of one window are not a group double-book.
- [x] **`MAX_ONE_LAB_PER_DAY` counts windows** per group per day.
- [x] **`LAB_ROTATION_COMPLETE`** — the batch↔subject rotation is a Latin square constructed from
  the grid (never searched); the validator rejects a duplicate (batch, subject) pairing.
- [x] **`SAME_SUBJECT_SAME_DAY` relaxed** — defaults to at most one LECTURE per subject per day,
  labs/tutorials exempt (the real timetable violates the old rule 160 times, all lecture+lab or
  lecture+tutorial pairings). Configurable via `include_session_types`.
- [x] **OR-Tools fixed** — calls `_expand_lab_batches`, models window co-location, propagates
  `batch_number`/`window_key` (was: half a timetable, zero practicals).
- [x] **Importer fixes** — faculty mapped by position within a cell's batch list (D3D4 SPS/PM →
  batch 3 = SPS, batch 4 = PM; the old `b-1` indexing gave every batch the same teacher), and
  3-letter glossary initials (SPS, VNS, HPK) are now captured.

**Measured (11 COMP divisions):** 21/30 windows fully co-located (all batches same day+slot, up
from 0); 21 windows carry 2+ subjects; COMP-TE-D day 0 = batches 1,2 on CG + 3,4 on IIS at the
same slot. Phase 1 metrics hold (0 break, 0 Saturday, 100% room stability). 9 scattered windows
are shared-faculty data gaps (unresolved initials — Phase 3).

---

## 🧪 Phase 3 — Honest demand and honest allocation (16 Aug 2026, A3/A9/B4/D6)

Fourth tranche of the DD-031 rebuild plan: the demand handed to the solver is now real, the
teachers are real, and no constraint fires on an invented number.

- [x] **Weekly hours come from the published grids** (`_derive_hours`, A3) — a division's
  assignment hours are the grid's own cell counts per subject; `_scheme_hours` is only the logged
  fallback where the grid is silent.
- [x] **Auto-fill demoted to `--fill-gaps`** — default import reports data gaps; `--fill-gaps`
  assigns the least-loaded teacher who holds a `faculty_subject_competency` row, stamped
  `source=AUTOFILL` (A9).
- [x] **`faculty_subject_competency` table** (faculty × subject, seeded from grid-derived
  assignments) — auto-fill and `_lab_batch_faculty` may only pick qualified teachers (B4).
- [x] **`profile_resources` pruned to assignment-holding teachers** — 3,710 → 96 rows (A9).
- [x] **`source` provenance** (`GRID | SCHEME | AUTOFILL`) on `subject_assignments`, surfaced as a
  per-cell badge in the assignments UI (C5).
- [x] **Invented-quantity constraints turned off** — `ROOM_CAPACITY_SUFFICIENT` and both faculty
  caps leave `STRUCTURAL_RULES`; a profile row re-enables them (D6). Measured: they rejected 0 of
  31,370 candidates before, so nothing changed on real data.
- [x] **Pre-solve feasibility report** (A4) — demand vs capacity per group/room-type/faculty is
  computed in `create_generation`; hard over-capacity fails the run with a 409 + report instead
  of completing with a warning string.
- [x] **OR-Tools fixed on real data** — window co-location uses presence indicators (the old
  per-pair equality was infeasible with 2+ room candidates → zero labs), `MAX_ONE_LAB_PER_DAY` is
  modelled relationally, `unplaced_count` counts committed sessions (B9), and the faculty caps
  honor the institutional toggle.

**Measured (11 COMP divisions, re-seeded with `--fill-gaps`):** 48 of 51 (subject, division)
pairs within ±1 hour of the published grid (the 3 misses are PROJECT — its grid cells name no
teacher at all); **0 teachers over cap** (was 2); `profile_resources` 3,710 → 96 rows; 154 GRID
+ 19 AUTOFILL assignment rows; 0 break-slot sessions, 0 Saturday, 100% in-venue, 0
(subject, group) duplicates. OR-Tools benchmark: COMP-TE-D 0 labs → 8 labs placed (23/27; the 4
unplaced are the shared-faculty window), COMP-SE-A 0 labs → 12 (29/33). 237 tests green.

---

## 🧪 Phase 3b — Make constraints editable, items 1–4 (16 Aug 2026, A10 / DD-042)

Fifth tranche of the DD-031 rebuild plan: the constraint boundary is drawn where the audit said
it was backwards — physics is always-on, policy is a tunable row, and every rule is reachable
through the API.

- [x] **`STRUCTURAL_RULES` split into `INVARIANT_RULES` + `DEFAULT_INSTITUTIONAL_RULES`** —
  physics (double-booking, cross-timetable conflicts, room requirements, availability,
  blackouts, break slots, lab-rotation integrity) stays always-on; policy (`SAME_SUBJECT_SAME_DAY`,
  `MAX_ONE_LAB_PER_DAY`, `CROSS_DEPT_DAILY_CAP`, `ROOM_CAPACITY_SUFFICIENT`, both faculty caps)
  fires only from a row. `ConstraintChecker.check_all` dispatches invariants only; configured
  rows dispatch everything else.
- [x] **College-default rows** — `hard_constraints.profile_id IS NULL` = applies to every
  profile. Migration `c9d4e8f2a6b0` seeds `SAME_SUBJECT_SAME_DAY` / `MAX_ONE_LAB_PER_DAY` /
  `CROSS_DEPT_DAILY_CAP` so nothing changes silently; the importer re-seeds the same rows after
  `--wipe` (which truncates `hard_constraints`). The faculty caps and room capacity are NOT
  seeded (DD-039: invented quantities).
- [x] **All previously-unreachable validators added to `ConstraintType`** — the 8 from A10 are
  now `POST /constraints/hard`-able (6 were still missing; Phase 3 had added the two faculty
  caps). **Startup assertion** `assert_registry_enum_parity()` raises if registry and enum ever
  drift again.
- [x] **`GET /constraints/types` returns tier + config JSON-schema** per type (from
  `CONSTRAINT_TIERS` / `CONFIG_SCHEMAS` in the registry) — the constraint editor UI renders a
  form from it; no code change needed to tune a rule.
- [x] **OR-Tools parity** — the `SAME_SUBJECT_SAME_DAY` relational constraint is gated on an
  active row, matching greedy's configured-rule dispatch.

**Measured:** 241 tests green (4 new: tier+schema catalog, registry/enum parity, institutional
rule off without a row / on with the college-default row). Live DB migrated; college-default
rows verified; regeneration of a published division behaves identically (slot counts unchanged
modulo the published cross-timetable reservations).

- [x] **Phase 3b item 5 — importer constants → institution facts document** (D2 / DD-043): the
  college's answers moved out of `scripts/import_tcet.py` into
  `CollegeSettings.config_json` — `scheme_hours` (L:3/T:1/P:2 fallback), `year_strengths`
  (per-year class strengths), `batches_per_year` (FE→3, SE+→2). The importer seeds missing keys
  ONCE at import start and reads them back, so `PUT /settings` edits win with no code change;
  `update_settings` now merges `config_json` key-by-key (a partial edit cannot clobber sibling
  keys like `max_cross_dept_per_day`). The import scope gate became the `--codes` CLI flag
  (default COMP; `--codes COMP,IT` re-admits IT at Phase 5). `lunch_break_after_slot` no longer
  exists (Phase 1); `default_block_length` already flowed through CONTIGUOUS_LAB_SLOTS rows.
- [x] **Measured after re-seed** — identical Phase 3 numbers (41 rooms, 392 faculty, 11 groups,
  30 subjects, 173 assignments = 154 GRID + 19 AUTOFILL, 100 competencies; 48/51 within ±1, the
  3 misses still PROJECT). 246 tests green (5 new). Live `PUT /settings` edit round-trips;
  college republished (11/11 COMP divisions).

**Phase 3b is COMPLETE.** The done-when — "a registrar can change max labs per day or the break
slot in the UI, no code change" — is backend-complete; the UI editor itself is scheduled with
Phase 6's frontend work. Next: **Phase 4 — Solve the cohort, not the division**.

---

## 🧪 Phase 4 — Solve the cohort, not the division — first tranche (16 Aug 2026, DD-044 / A4 / A6)

The audit's "one division at a time, published-sequentially" and "one-shot greedy" findings,
attacked from the data side first.

- [x] **DD-044 — the cell parser reads position** — lab faculty sit between the batch pattern
  and the room (no glossary gate), the subject is the first legend-code token with long forms
  included, lecture faculty sit between subject and room gated by known initials. The old gate
  dropped every pair's second initial ("Lab CG D3D4 SuS/HP" → [SuS]) and mis-took a faculty
  initial that collides with a subject code as the subject ("IIS MP 608" → subject MP) —
  inflating TE-B's MP to 6h and deleting its IIS lectures. `parse_cell` moved to
  `scripts/cell_parser.py` (unit-testable without re-running the adapter).
- [x] **DD-044 — single-teacher batch pairs merge in the solver** — window members that share
  (subject, faculty) ("Lab DWM A1A2 SG") merge into ONE session covering the pair, so the
  window co-locates instead of failing and scattering its members (which saturated
  `MAX_ONE_LAB_PER_DAY` and left members unplaced).
- [x] **A6 — fail-fast `is_valid`** — the acceptance test returns on the first violation;
  `check_all` keeps the full report for diagnostics.
- [x] **A6 — most-constrained-first ordering** — sessions sort by room scarcity × faculty
  demand × group load × block size instead of two booleans.
- [x] **A6 — quality is the default** — with soft rules active every seeded attempt is scored
  and the best-scoring distinct one is kept, for every variation.
- [x] **A4 — published faculty load feeds the caps** — `_load_published_conflicts` returns
  per-faculty day/week counts; `FACULTY_MAX_HOURS_PER_DAY/WEEK` measure candidate + committed +
  published, so caps compose across runs.
- [x] **Deferred with measurement** — the committed-slot index refactor: fresh solves of all 11
  divisions take 0.55s total, so the linear scans are not yet the bottleneck.

**Measured (11 COMP divisions, fresh solves):** **unplaced 10 → 0** (0.55s total, well under
the minute-per-cohort budget); hours-per-(subject, division) 3/53 outside ±1, all PROJECT (the
honest no-mentor gap); all 11 divisions republished with zero unplaced sessions; 256 tests
green (11 new: parser rules, pair merging, fail-fast, published-load caps, published counts).

**Remaining in Phase 4:** cohort profiles — one generation per (department, year) — which is a
product-shape decision (how a cohort instance maps to the per-division UI) needing DD-045; and
construct-then-repair LNS (A11).

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
- [x] **One timetable per class (demo seed goal)**: `scripts/generate_college.py` generates + publishes a timetable for EVERY class — 192 instances (12 demo departments × 4 years × 4 divisions), each exactly one division's clean timetable (24-25 sessions). Ran clean: 192/192 published, ~4700 slots total. **This runs the fabricated demo data — the real-data rollout is the plan in `documentation/real-data-rollout-plan.md`.** (`--only`, `--dry-run`, `--clear-locks` options.)
- [x] **Security audit (DD-029)**: see "Newly Identified" — role gates, least-privilege registration, hardened error/upload/header surfaces, `/generate` rate limit, JWT-expiry check. 209 tests.
- [ ] **CSV upload modals** (part of Resource Management).
- [x] **Assignment grid**: `/assignments` — a subject × group matrix scoped by department + semester (rows = subjects, columns = division groups), with faculty avatar + weekly-hours badge per cell, an anchored cell editor (assign/change faculty + hours, remove), per-subject coverage chips, and a least-loaded-faculty **Auto-fill unassigned** bulk action. Drives the same `subject_assignments` CRUD the solver reads.
- [x] **Profile & Constraint Builder**: `/profiles` (card grid of presets with create drawer + archive) and `/profiles/[id]` (four tabs: **Resources** per-type shuttles, **Parameters** catalog-driven key/value rows with JSON validation, **Constraints** hard + soft rows from the `GET /constraints/types` catalog with inline soft-weight editing, **Runs** generation history). The Generate button preselects the profile via `?profile=N`.
- [ ] **Instance Editor**: Click-to-edit slots with live conflict re-checking. *(Core done — see "Slot override UI"; polish left.)*

### 🔵 Deployment & Final Polish
- [x] **Full Stack Dockerization**: top-level `docker-compose.yml` (App, Frontend, PostgreSQL, Redis) + backend `Dockerfile` (uv, migrates on boot) + `frontend/Dockerfile` (standalone Next). `docker/docker-compose.yml` remains the backend-only dev infra (DD-018). *(`docker compose up` four-service bring-up pending on a free host port 3000 — see DD-018 follow-up.)*
- [x] **Scale battle test**: `scripts/seed_demo.py` seeds a 12-department **fabricated demo** college loosely modeled on the TCET timetable *shape* (16 classes per department, 492 subject streams, 1976 faculty, 192 groups, 324 rooms, 1968 assignments, 204 profiles). `scripts/battle_test.py`, `scripts/api_drive.py`, `scripts/async_drive.py` run real generations (greedy + OR-Tools, sync + async Celery, generation lock, publish → cross-timetable safety) against live Postgres/Redis. Surfaced and fixed three real bugs: unfiltered multi-group PDF export (ReportLab `LayoutError`), `GenerationResponse` omitting `run_duration_ms`, and the greedy solver packing a class into the minimum days (empty Mon/Thu/Sat) instead of spreading across the week. See DD-020. **The department list, FE scheme, strengths, faculty counts, and rooms are demo fabrications — replace per `documentation/real-data-rollout-plan.md`.**
- [x] **Full-features-at-scale verification**: `scripts/full_stack_test.py` re-verifies every capability at whole-department scale (soft pursuit, `MAX_DAILY_SUBJECTS`/`ALLOW_FREE_LAST_SLOT`, OR-Tools relational rules + greedy fallback, honest `hard_violations`/`placement_warning`, RBAC, conflict audit, real Celery async path). Surfaced and fixed: OR-Tools returning 0 slots on a big relational-rule profile (now greedy-fallback), and duplicate admin names 500ing (now 409).
- [ ] **README & Docs**: Setup guide, architecture diagram link, API examples.
- [ ] **Historical Data Import**: Upload past semesters' timetables for pattern reference.
- [ ] **ML Preference Learning (Phase 2)**: Learn from manual overrides to suggest constraints automatically.

---

> **How to use this file:** Check off items (`- [x]`) as they are merged into `main`. Use the color coding to prioritize your next sprint (🔴 Critical → 🟠 Engine → 🟡 Polish).
