# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

## Session summary (committed & pushed)

State at handoff: **63/63 tests passing** (`uv run python -m app.tests`), tree clean.

This session implemented the **`HOLIDAY_CALENDAR` registry rule** (the "NEXT TASK" from the
previous handoff, also `documentation/plan.md` Phase 2 / `progress.md` → registry rules).

1. **`app/models/constraints.py`** — added `ConstraintType.HOLIDAY_CALENDAR` to the catalog
   and `HARD_CONSTRAINT_TYPES`, so `GET /constraints/types` surfaces it automatically. No
   schema migration (constraint types are plain strings).
2. **`app/engine/constraint_registry.py`** — registered `_holiday_calendar`, a date-matching
   validator. `config_json` shape decided: `{"holidays": ["2025-01-26", ...]}` (ISO date
   strings). It compares each candidate's materialized `slot_date` against the list and
   returns a reason on a match; a slot with no materialized date (no `term_start` anchor)
   is a **no-op**, so a profile without `term_start` never blanks out every week. This
   mirrors the date-bounded availability-window rule.
3. **Both solvers wired for free through the shared registry** — greedy validates every
   candidate via `ConstraintChecker._check_configured`; OR-Tools prunes the variable domain
   with the same static checker (empty committed set), so `HOLIDAY_CALENDAR` blocks the
   holiday's weekday in both. No solver edits were needed.
4. **Tests** — 5 new (58 → 63): validator unit (blocked date / non-listed date / no
   `slot_date` / empty config), greedy end-to-end (holiday weekday absent, slots still
   materialize dates), outside-term holiday ignored, no-`term_start` anchor inert, and
   OR-Tools prunes the holiday from its domain.

Commits (pushed to `main`): `59ec02f` (engine), `9cf714e` (tests), `eee3da8` (docs).

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, architecture notes, commit rules.
- `documentation/timetable-generator-architecture.md` — §3.3 (registry table incl.
  `HOLIDAY_CALENDAR`), §5.2 (OR-Tools static pruning list), §8.2 (hard-constraint
  reference), §8.8 (calendar-date anchoring + how HOLIDAY_CALENDAR reuses it), §6.2
  (combination merge semantics), §4.2 / §7.4 (auth posture).
- `documentation/plan.md` and `documentation/progress.md` — "New Constraint Types" now reads
  "5 of 5 done"; `CONTIGUOUS_LAB_SLOTS` and `EXAM_DATE_SEPARATION` remain as separate
  catalog members.
- Registry rules pattern: `app/engine/constraint_registry.py` (`hard_rule` decorator +
  `HARD_CONSTRAINT_REGISTRY`), the validator signature `(candidate, committed, config, ctx)
  -> str | None`, and `ConstraintChecker._check_configured` dispatch.
- Calendar-date foundation: `GreedySolver._parse_term_start` / `_materialize_slot_date`
  (`app/engine/solvers/greedy_solver.py`), `term_start` profile param (§8.8).
- Tests: `app/tests/test_settings_and_assignments.py` (Phase 2 registry suite,
  Phase 3 OR-Tools suite), `app/tests/test_runner.py` (`seed_minimal`), `app/tests/conftest.py`.

## NEXT TASK — `CONTIGUOUS_LAB_SLOTS` registry rule (multi-slot sessions)

`HOLIDAY_CALENDAR` was the first of the pending registry rules; the remaining catalog
members are deeper engine changes:

- **`CONTIGUOUS_LAB_SLOTS`** (plan.md Phase 2) — today every session occupies exactly one
  slot (`SessionToSchedule` expands an assignment into N one-slot sessions; see
  `GreedySolver._build_sessions`). This rule needs the engine to model *multi-slot* lab
  sessions: a lab block that spans 2+ consecutive slots in the same room/group/teacher.
  That is a deep change — session expansion, the slot grid, double-booking checks
  (currently per single slot), and OR-Tools relational constraints all assume one slot per
  session. Decide the `config_json` shape (e.g. which subjects/labs and how many slots per
  block), then pick a representation (a "block" spanning `slot_number .. slot_number + k`)
  and wire it through both solvers.
- **`EXAM_DATE_SEPARATION`** — needs an exam-domain notion (minimum days between exams for a
  group); currently no exam table/rule exists, so this likely needs a model decision first.

## Remaining known items (see `documentation/progress.md`)

- **Registry rules** — `CONTIGUOUS_LAB_SLOTS` (next, above), `EXAM_DATE_SEPARATION`.
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
  patch loop in `app/tests/conftest.py`.
- **The auth gate is global**: tests that call a non-exempt route must pass
  `auth_headers(login_token(client))`. Only `/health` and `/auth/*` are exempt; `/docs`,
  `/openapi.json`, and every read route return 401 without a token.
- The solver constructors take a `ResolvedProfile`, not `profile_id` — build one via
  `ProfileResolver(db).resolve(profile_id, combination_id)` if you construct solvers
  directly outside the scheduler.
- Registry validators are static per-candidate in OR-Tools only if they don't read
  `committed_slots`; committed-dependent rules (like `MAX_CONSECUTIVE_SAME_TEACHER`) are
  only enforced by the final full-checker pass and can drop placements. If `CONTIGUOUS_LAB_SLOTS`
  is committed-dependent, plan the OR-Tools story (domain pruning + post-pass, as today).
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8).
- Alembic head: `e9f4a2b6d8c0`. 22 tables. No migration was needed this session.
