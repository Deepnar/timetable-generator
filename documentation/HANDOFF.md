# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

## Session summary (committed & pushed)

State at handoff: **50/50 tests passing** (`uv run python -m app.tests`), tree clean.

This session fixed the faculty availability date-range bug plus three more of the
"Newly Identified" items from `documentation/progress.md`:

1. **Faculty availability date-range** — `effective_from`/`effective_to` were never
   consulted and were `nullable=False` against optional schemas.
   - Migration `e9f4a2b6d8c0`: both columns nullable (new Alembic head).
   - New **`term_start`** profile parameter (`"YYYY-MM-DD"`) anchors the weekly
     template; `GreedySolver._materialize_slot_date(day)` stamps `slot_date` on every
     `SlotCandidate` and committed `TimetableSlot` (both greedy and OR-Tools).
   - `ConstraintChecker._check_teacher_availability` now filters by the window;
     `_availability_window_applies` encodes: no bounds ⇒ timeless; bounded ⇒ only when
     `effective_from <= slot_date <= effective_to`; no anchor ⇒ inert (matches
     date-specific `room_blackouts`). See architecture §8.8.
2. **CSV import atomicity** — `app/router/import_csv.py::_atomic_import` makes
   `/import/{rooms,faculty,groups,subjects}` all-or-nothing: any invalid row (missing
   required field, duplicate within the file OR against the DB) ⇒ `422`, `inserted=0`,
   nothing committed. `import_rooms` now requires a non-empty `room_code`.
3. **`GET /constraints/types` drift** — the endpoint now derives hard/soft lists from
   `HARD_CONSTRAINT_TYPES` / `SOFT_CONSTRAINT_TYPES` defined next to the `ConstraintType`
   enum in `app/models/constraints.py`.
4. **Slot override re-validation** — `PATCH /instances/{id}/slots/{slot_id}` now runs the
   full `ConstraintChecker` (`_revalidate_slot` in `app/router/instances.py`) against the
   instance's other slots, the profile's registry rules, and published cross-timetable
   reservations; a conflict returns `409` and leaves the slot untouched.

Commits: `5c78e5c` `2fdc2be` `ce601d1` `314abdb` `fe86b5b` (availability fix), then the
three bug fixes in the commit log of this session (engine/tests/docs split per AGENTS.md).

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, architecture notes, commit rules.
- `documentation/timetable-generator-architecture.md` — schema §3, endpoints §4, engine §5,
  parameters §8 (esp. §8.8 calendar-date anchoring, new).
- `documentation/plan.md` (phased roadmap) and `documentation/progress.md` (status).
- Engine: `app/engine/scheduler.py`, `app/engine/solvers/greedy_solver.py`,
  `app/engine/solvers/or_tools_solver.py`, `app/engine/constraint_checker.py`,
  `app/engine/constraint_registry.py`, `app/engine/scorer.py`, `app/engine/soft_objective.py`.
- Tests: suites in `app/tests/test_settings_and_assignments.py`, runner in
  `app/tests/test_runner.py`, DB override in `app/tests/conftest.py`. Hand-rolled, **not** pytest.

## NEXT TASK — profile combination resolution

**The bug:** `POST /profiles/combine` stores members in `profile_combination_members`, but
`Scheduler.run()` (`app/engine/scheduler.py`) only ever reads `profile_id`. `POST /generate`
accepts `combination_id`, yet generating from a combination fails because the solver gets no
resolved profile. The endpoint currently misleads.

**Where to look:**
- `app/router/profiles.py` — the `/combine` endpoint and member storage.
- `app/engine/scheduler.py::run` — takes both `profile_id` and `combination_id`; ignores the latter.
- `app/engine/solvers/greedy_solver.py` / `or_tools_solver.py` — constructors take a single `profile_id`.
- `app/models/profiles.py` — `ProfileCombination`, `ProfileCombinationMember` (has `weight`).
- `app/models/generation.py` — `TimetableGeneration.combination_id` already exists.

**Suggested approach:** resolve a combination into an effective profile before solving:
merge member `profile_resources` (union, de-dup by `(resource_type, resource_id)`), merge
`profile_parameters` (highest `weight` wins on key collisions), merge member + profile-level
`hard_constraints`/`soft_constraints`, then pass the effective profile id/params to the solver.
Decide and document collision semantics. Add tests in `app/tests/test_settings_and_assignments.py`.

## Remaining known items (see `documentation/progress.md`)

- **Read-route auth inconsistency** — `/settings` GET requires a token, most GETs don't.
  Product decision: protect everything except `/health` + `/auth/*`, or leave reads public?
  Fully authenticated is the likely direction; it requires updating tests that GET without headers.
- **Registry rules** — `HOLIDAY_CALENDAR` (date-matching validator only; the
  `term_start`/`slot_date` machinery from this session is the foundation), `CONTIGUOUS_LAB_SLOTS`
  (multi-slot sessions — deep engine change), `EXAM_DATE_SEPARATION`.
- **Async generation** — Celery/Redis; `GET /generate/{id}/status` already exists.
- **OR-Tools diversity** — objective-based variation (best / minimize-teacher-gaps / minimize-student-gaps).
- **Flexibility roadmap** — fold structural checks into the registry, generic resource
  requirements, `CUSTOM` enum escape hatches, wire `enable_lab_batches`.
- **Frontend + full-stack Dockerization** — Next.js app + top-level compose.

## Gotchas

- Postgres runs on host port **5433** (`.env` sets `DB_PORT=5433`); `docker/docker-compose.yml` maps it.
- Tests: `uv run python -m app.tests` (not pytest). Add any router touched by tests to the
  patch loop in `app/tests/conftest.py`.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8).
- Alembic head: `e9f4a2b6d8c0`. 22 tables.
