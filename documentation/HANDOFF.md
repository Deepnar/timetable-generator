# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

## Session summary (committed & pushed)

State at handoff: **74/74 tests passing** (`uv run python -m app.tests`), tree clean.

This session implemented the **`CONTIGUOUS_LAB_SLOTS` registry rule** (the "NEXT TASK" from
the previous handoff, also `documentation/plan.md` Phase 2 / `progress.md` → registry rules).
This was a *deep engine change* — the first time a session occupies more than one slot.

1. **Representation** — `SessionToSchedule.block_length` (default 1) and
   `SlotCandidate.block_length` + a `slot_numbers` range. A block spans
   `slot_number .. slot_number + k - 1` in the same room/teacher/group on one day and is
   committed as `k` `TimetableSlot`s.
2. **Config shape** — `config_json`: `{"block_lengths": {"<subject_id>": int}, "default_block_length"?: int}`.
   `block_lengths` pins specific lab subjects to a block size (JSON keys are strings; int
   ids also match); `default_block_length` applies to every lab subject not listed. The
   single resolver `configured_block_length()` lives in `app/engine/constraint_registry.py`
   and is shared by the expansion and the validator. Restrictive: it only applies to
   `requires_lab` subjects.
3. **Expansion** — `GreedySolver._lab_block_lengths()` reads the rule off the resolved
   profile; `_build_sessions()` splits a governed lab assignment's `weekly_hours` into
   full blocks (`// length`) plus a single-slot remainder, so 4 hours at length 3 becomes
   one 3-slot block + one single session. OR-Tools reuses the same `_build_sessions`.
4. **Checker** — teacher/room/group double-book and `_check_published_conflicts` now fire
   if *any* sub-slot collides (`s.slot_number in c.slot_numbers`); `_check_faculty_load`
   counts the block's full length. Time-window rules (unavailability, room blackout)
   already overlap-check the whole span via start/end time, so they needed no change.
   `SAME_SUBJECT_SAME_DAY` naturally allows one block per subject per group per day.
5. **Registry rules made block-aware** — `SUBJECT_TIME_PREFERENCE` bounds the block's
   *last* slot by `max_slot` and first by `min_slot`; `MAX_CONSECUTIVE_SAME_TEACHER`
   counts the block as one contiguous run (committed ∪ block range, walk left/right).
   `_contiguous_lab_slots` itself is a consistency guard (a block candidate must match its
   explicitly-configured size; `default_block_length` subjects are not validated — the
   solver always forms default-sized blocks anyway).
6. **OR-Tools** — block sessions get variables keyed by their **start** slot
   (`x[si, day, start, room]`, domain-pruned by the static checker with the full block
   span), register in the double-book buckets for *every* occupied slot, contribute
   `block_length`× to the daily/weekly load buckets, and are committed only if the
   committed-aware final pass validates the whole block. `by_group_subject_day` stays
   one-registration so CP-SAT matches greedy's one-block-per-subject-per-day.
7. **Tests** — 11 new (63 → 74): config resolution, size-guard validator, block-aware
   `SUBJECT_TIME_PREFERENCE`/`MAX_CONSECUTIVE`, greedy blocks (contiguous / remainder /
   `default_block_length` / no-rule fallback), checker block overlap, and OR-Tools
   block production. `seed_minimal` gained `requires_lab` and `weekly_hours` options and
   sizes the group to fit the lab room (strength 40) so lab sessions are schedulable.

Commits (pushed to `main`): `7a2503c` (engine), `2bd3179` (tests), `9315ddc` (docs).
No migration was needed — `CONTIGUOUS_LAB_SLOTS` was already in the `ConstraintType`
catalog and the constraint table is string-typed.

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, architecture notes, commit rules.
- `documentation/timetable-generator-architecture.md` — §3.3 (registry table incl.
  `CONTIGUOUS_LAB_SLOTS`), §5.2 (new "Multi-slot lab sessions (`CONTIGUOUS_LAB_SLOTS`)"
  subsection, plus the updated static/relational split), §8.2 (hard-constraint reference),
  §8.8 (calendar-date anchoring), §6.2 (combination merge semantics), §4.2 / §7.4 (auth
  posture).
- `documentation/plan.md` and `documentation/progress.md` — "New Constraint Types" now reads
  "6 of 7 done"; `EXAM_DATE_SEPARATION` remains the only pending catalog member.
- Registry rules pattern: `app/engine/constraint_registry.py` (`hard_rule` decorator +
  `HARD_CONSTRAINT_REGISTRY`), validator signature `(candidate, committed, config, ctx)
  -> str | None`, `configured_block_length()` helper, and `ConstraintChecker._check_configured`
  dispatch.
- Block-aware engine: `SessionToSchedule.block_length` / `_lab_block_lengths` /
  `_build_sessions` / `solve()` (`app/engine/solvers/greedy_solver.py`),
  `SlotCandidate.block_length` / `slot_numbers` and the block-aware double-book /
  published-conflict / load checks (`app/engine/constraint_checker.py`), and the
  start-slot-keyed variables + per-sub-slot buckets (`app/engine/solvers/or_tools_solver.py`).
- Tests: `app/tests/test_contiguous_lab_slots.py` (new Phase 2 suite, registered in
  `app/tests/__main__.py`), `app/tests/test_settings_and_assignments.py` (registry /
  OR-Tools suites), `app/tests/test_runner.py` (`seed_minimal` with `requires_lab` /
  `weekly_hours`), `app/tests/conftest.py`.

## NEXT TASK — `EXAM_DATE_SEPARATION` registry rule (exam domain)

`CONTIGUOUS_LAB_SLOTS` was the last of the pending *engine-shaped* rules; the only
remaining catalog member needs a domain decision first:

- **`EXAM_DATE_SEPARATION`** — a minimum number of days between two exams for the same
  group. Today there is **no exam table or exam-domain notion** in the engine: slots are
  weekly-template recurring (`day_of_week`/`slot_number`) and `SessionType.EXAM` exists
  only as an enum value. This rule likely needs a **model decision first** — e.g. a
  dedicated exam-scheduling path (concrete dates, per-group exam slots) or reusing the
  existing `TimetableSlot.slot_date` for one-off date-based placements. Decide the data
  shape before writing the validator; both solvers' weekly-template assumptions will
  need revisiting.

## Remaining known items (see `documentation/progress.md`)

- **Registry rules** — `EXAM_DATE_SEPARATION` (next, above; needs a model decision first).
- **Async generation** — Celery/Redis; `GET /generate/{id}/status` already exists.
- **OR-Tools diversity** — objective-based variation (best / minimize-teacher-gaps /
  minimize-student-gaps).
- **Flexibility roadmap** — fold structural checks into the registry, generic resource
  requirements, `CUSTOM` enum escape hatches, wire `enable_lab_batches`.
- **Frontend + full-stack Dockerization** — Next.js app + top-level compose.
- **`/profiles/combinations` router** — still no list endpoint and no explicit
  `POST /profiles/combinations/{id}/resolve` (resolution is automatic inside the scheduler);
  tracked in `plan.md`.

## Gotchas

- Postgres runs on host port **5433** (`.env` sets `DB_PORT=5433`); `docker/docker-compose.yml` maps it.
- Tests: `uv run python -m app.tests` (not pytest). Add any router touched by tests to the
  patch loop in `app/tests/conftest.py`. New test modules must be imported in
  `app/tests/__main__.py` to register their suites.
- **The auth gate is global**: tests that call a non-exempt route must pass
  `auth_headers(login_token(client))`. Only `/health` and `/auth/*` are exempt; `/docs`,
  `/openapi.json`, and every read route return 401 without a token.
- The solver constructors take a `ResolvedProfile`, not `profile_id` — build one via
  `ProfileResolver(db).resolve(profile_id, combination_id)` if you construct solvers
  directly outside the scheduler.
- Registry validators are static per-candidate in OR-Tools only if they don't read
  `committed_slots`; committed-dependent rules (like `MAX_CONSECUTIVE_SAME_TEACHER`) are
  only enforced by the final full-checker pass and can drop placements. Blocks inherit this
  caveat.
- Block-specific limitations to remember: `_check_cross_dept_cap` still counts committed
  *slots* (a committed block contributes its length to the per-day cross-dept tally), and
  the CP-SAT soft objective builders (`TEACHER_PREFERS_MORNING`, `MINIMIZE_STUDENT_FREE_SLOTS`)
  key placements by a block's **start slot** only.
- A lab block counts as `block_length` hours against `max_hours_per_day`/`max_hours_per_week`,
  so a block larger than a teacher's remaining daily cap is correctly unschedulable.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8).
- Alembic head: `e9f4a2b6d8c0`. 22 tables. No migration was needed this session.
