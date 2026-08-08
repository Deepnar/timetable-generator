# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

## Session summary (committed & pushed)

State at handoff: **114/114 tests passing** (`uv run python -m app.tests`), tree clean.
Postgres at Alembic head `d7a3c5e9f1b2` (the two new migrations were applied live).

This session completed the **flexibility roadmap** (the top-ranked NEXT TASK from the
previous handoff). All four levers from plan.md are now shipped:

1. **Structural checks folded into the registry** (commit `3c30e04`) — the always-on core
   rules (double-book ×3, cross-timetable ×3, capacity, room requirements, availability,
   faculty load ×2, blackouts, same-subject, cross-dept cap — 14 rules) are now registered
   validators in `app/engine/constraint_registry.py` (`STRUCTURAL_RULES` tuple),
   dispatched by `ConstraintChecker.check_all` on every candidate regardless of the
   profile's `hard_constraints` rows. Rows of a structural type are decorative; a profile
   cannot switch a structural rule off. `ConstraintContext` now carries `settings` +
   `reserved` + cached row lookups.
2. **Generic room requirements** (commit `19929d6`) — `Subject.requires_lab` (binary) is
   replaced by declarative `Subject.requirements_json` (`room_types` / `min_capacity` /
   `features` / `session_type`) matched against `Room.equipment_json` + legacy boolean
   columns by the new `app/engine/resource_requirements.py`. `requires_lab` is now just
   shorthand for `{"room_types": ["LAB"]}`. The registry rule `ROOM_TYPE_MATCH` was renamed
   `ROOM_REQUIREMENTS_MET`; both solvers pick rooms through `room_matches_requirements`
   instead of hardcoding `room_type == LAB`. CSV import accepts the new JSON columns
   (`_optional_json` helper). New migration `c2e8a4d6f0b1`.
3. **`enable_lab_batches` wired** (commit `777220f`) — `_lab_batch_rotation` now consults
   the `CollegeSettings.enable_lab_batches` flag: with it off (the default) the rule is
   inert, making lab-batch rotation opt-in. (`enable_soft_constraint_scoring` was already
   wired everywhere.)
4. **`CUSTOM` escape hatches** (commit `b9492be`) — `CUSTOM` added to `RoomType` and
   `SessionType` (migration `d7a3c5e9f1b2`, `ALTER TYPE ... ADD VALUE` on Postgres).
   `GroupType` already had `CUSTOM`; free-form attributes hang off
   `equipment_json`/`requirements_json`.

**Tests** — **13 new (101 → 114)** in `app/tests/test_flexibility.py` (registered in
`app/tests/__main__.py`): `effective_requirements` / `subject_session_type` /
`room_matches_requirements` unit coverage; solver integration (a subject requiring a LAB
room lands on the lab; a declared `session_type` lands on the slot; no matching room →
zero sessions); the `enable_lab_batches` gate (rule inert off, enforces on, via a real
`ConstraintContext`); the CUSTOM enum values; and API + CSV round-trips for the new JSON
columns.

**Docs** (commit `d8c95ba`) — architecture doc gained §5.5 (Generic room requirements),
the renamed rule + gate notes in §3.3, the new columns + CUSTOM enum values in §3, the
migration chain bumped to head `d7a3c5e9f1b2`, endpoint input notes in §4, and
`requirements_json`/`equipment_json` rows in §8.4. plan.md and progress.md tick the
flexibility items.

**Commits (in order):** `3c30e04` (registry fold — engine+checker), `19929d6` (generic
requirements — engine+models+schemas+import+migration), `777220f` (flag gate),
`b9492be` (CUSTOM enums — models+migration), `ef009ac` (tests), `d8c95ba` (docs).

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, commit rules.
- `documentation/timetable-generator-architecture.md` — **§5.5 (Generic room
  requirements)**, §3.3 (constraint catalog incl. `ROOM_REQUIREMENTS_MET` +
  `STRUCTURAL_RULES`), §3 (schema incl. new columns + migration chain to
  `d7a3c5e9f1b2`), §5.1 step 3 (session build), §4 (rooms/subjects endpoints).
- `app/engine/constraint_registry.py` — `STRUCTURAL_RULES`, `ConstraintContext`,
  `HARD_CONSTRAINT_REGISTRY`, the `@hard_rule` decorator, `_lab_batch_rotation` gate.
- `app/engine/resource_requirements.py` — the requirements spec + matching.
- `app/engine/constraint_checker.py` — the delegating checker (runs `STRUCTURAL_RULES`
  then `_check_configured`).
- Tests: `app/tests/test_flexibility.py`, `app/tests/test_runner.py` (`seed_minimal`),
  `app/tests/conftest.py` (patch loop), `app/tests/__main__.py`.

## NEXT TASK — the flexibility roadmap is DONE. Next up: **Redis Integration**

The remaining roadmap items in priority order (details in `documentation/progress.md`):

1. **Redis Integration** — the highest-priority open item. Redis already runs in
   `docker/docker-compose.yml` and is the Celery broker/backend. Open usages:
   - Cache frequent GETs (rooms/subjects/profiles lists, settings) with invalidation on
     write.
   - Rate limiting on auth endpoints.
   - **Generation-conflict locking**: a `redis_lock` around `solve_generation` keyed by
     resource ids so two simultaneous runs can't double-book the same faculty/room/group.
2. **Email Notifications on Publish** — SMTP + mail to faculty (personal PDF), HOD
   (summary), class incharges on `POST /instances/{id}/publish`.
3. **API Polish** — pagination completeness, global error middleware, request
   logging/audit, API versioning (`/api/v1/`). (Global auth gate is done.)
4. **Frontend (Next.js/React) + full-stack Dockerization** — the planned UI
   (`documentation/plan.md` Phase 4 + progress.md 🟢): auth & dashboard, resource CRUD,
   assignment grid, profile/constraint builder, generation viewer, instance editor. Plus a
   top-level compose running App + Frontend + PostgreSQL + Redis.
5. **Final polish** — README/setup guide, historical data import, ML preference learning
   (Phase 2, from manual overrides).

## Remaining known items (see `documentation/progress.md`)

- **Redis Integration** — caching, rate limiting, generation-conflict locking.
- **Email Notifications on Publish** — SMTP, faculty/HOD/incharge mail on publish.
- **API Polish** — pagination, global error middleware, request logging/audit, `/api/v1/`.
- **Frontend + full-stack Dockerization** — Next.js app + top-level compose.
- **README & Docs, Historical Data Import, ML Preference Learning**.
- **`TimetableType` still lacks a `CUSTOM` label** — the roadmap levers 3/4 were scoped to
  room/session types (the ones the solver branches on); `timetable_generations.timetable_type`
  is still `CLASS | FACULTY | ROOM | EVENT | EXAM | IP` (native enum). Add `CUSTOM` the same
  way as `d7a3c5e9f1b2` if a caller needs a free-form timetable kind.

## MINI-PLAN for the next session (Redis Integration)

Follow exactly; commit per concern (migration / engine / API / tests / docs separate).

1. **Scope it.** Read `documentation/progress.md` 🟡 "Redis Integration", `app/engine/scheduler.py`
   (`solve_generation`), `app/tasks/generation.py`, and how `app/config.py` reads Redis/async env.
   Decide the minimal, testable slice. Recommendation: start with **generation-conflict locking**
   (the one that prevents real double-bookings), then cache hot GETs, then rate limiting.
2. **Add a redis client module** (`app/services/redis_client.py` or similar) that reads the
   Redis URL from config, is lazy/optional (returns a no-op when Redis is down or
   `ASYNC_GENERATION=false`), and exposes `acquire_lock(key, timeout)` / `release_lock`.
   The test suite has no Redis, so every Redis call path must degrade gracefully.
3. **Wire the lock into `Scheduler.solve_generation`.** Around the solve, acquire a lock
   keyed by the run's resource ids (or a coarse `generate:{academic_year}:{semester}` key),
   with a timeout; on `LockError` mark the run FAILED with `error_log` or return 409 in the
   router. Do NOT break the existing sync path when Redis is absent.
4. **Cache hot GETs** (rooms/subjects/profiles/settings list responses). Cache-bust on the
   matching POST/PUT/DELETE. Keep `TestClient` semantics intact — the suite hits the DB
   through the patch loop, so caching must be off or inert in tests.
5. **Add a rate limiter** to `/auth/login` and `/auth/register` (e.g. fixed-window counter
   per IP in Redis). Inert without Redis.
6. **Tests** — add a new module `app/tests/test_redis_integration.py` (register in
   `app/tests/__main__.py`). Simulate a fake/in-memory Redis or a stub `redis_client` so the
   suite stays Redis-free; verify the lock actually excludes a concurrent solve and that a
   downed Redis degrades to no-lock behaviour. Run `uv run python -m app.tests` — must stay
   114/114 + new.
7. **Docs** — update architecture §7 (async/infra) + §4.2 endpoints + `plan.md`/`progress.md`
   checkboxes in the same change. Commit separately.
8. **Commit & push**, then overwrite this HANDOFF with the new session summary + a fresh
   mini-plan for the *next* item.

## Gotchas

- Postgres runs on host port **5433** (`.env` sets `DB_PORT=5433`); Redis maps `6379`.
  Alembic head: `d7a3c5e9f1b2`. 22 tables.
- Tests: `uv run python -m app.tests` (not pytest). Add any router touched by tests to the
  patch loop in `app/tests/conftest.py`. New test modules must be imported in
  `app/tests/__main__.py` to register their suites. **No Redis/Celery in tests** — stub or
  fake anything network-dependent.
- **Literal sub-routes under `/profiles` must be registered before `/{id}`** (Starlette
  path params match any single segment → a later `"combinations"` list route gets shadowed
  and returns 422). See the comment above `get_profile_combinations`.
- **Native Postgres enum migration gotcha:** `roomtype`/`sessiontype` (and any native enum)
  can only be extended with `ALTER TYPE ... ADD VALUE` inside `upgrade()` — never drop and
  recreate (the column references the type). `d7a3c5e9f1b2` is the pattern. `downgrade()` is
  a documented no-op because Postgres cannot remove a label.
- **Structural rules are always-on**: the 14 `STRUCTURAL_RULES` are dispatched regardless of
  profile `hard_constraints` rows; a row of a structural type is decorative. New *data-driven*
  rules must be registered with `@hard_rule` AND their enum member added to
  `HARD_CONSTRAINT_TYPES` (the `GET /constraints/types` catalog test asserts exact
  enum ↔ list parity).
- **`requirements_json` semantics:** an empty dict means "no constraints" even with
  `requires_lab=True`; a missing `features` tag is unsatisfiable unless the room carries it
  in `equipment_json` or a legacy boolean (`projector`/`ac`); a subject whose requirements
  match no profile room schedules zero sessions (greedy warns, never uses a wrong room).
- **Async mode is off by default** (`ASYNC_GENERATION=false`). Worker task tests call
  `run_generation(run_id)` directly; the async HTTP branch uses
  `celery.current_app.conf.task_always_eager = True`.
- **The auth gate is global**: tests that call a non-exempt route must pass
  `auth_headers(login_token(client))`. Only `/health` and `/auth/*` are exempt.
- **Variation semantics:** instance #1 is the deterministic baseline (seed `None`) unless
  `variation="best"`; gap criteria only reshape *seeded* re-rolls; keep `PLACEMENT_WEIGHT`
  strictly above any soft/variation term so placements are never traded away.
- **Exam specifics:** `EXAM_DATE_SEPARATION` only matters with `term_start`; OR-Tools models
  the rule relationally (§5.2) and the final full-checker pass is the safety net for other
  committed-dependent registry rules.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md` checkboxes.
