# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

## Session summary (committed & pushed)

State at handoff: **101/101 tests passing** (`uv run python -m app.tests`), tree clean, pushed.

This session implemented the **`/profiles/combinations` router** (the top-ranked NEXT TASK
from the previous handoff). Combination resolution was previously invisible — `POST
/generate` merged members automatically inside the scheduler with no way to list them or
preview a run. Two endpoints now sit in `app/router/profiles.py`:

1. **`GET /profiles/combinations`** — lists every combination (newest first) with its
   member profiles (id, name, weight, `is_active`) and a cheap `resolution_status` preview:
   `RESOLVABLE` / `INACTIVE_MEMBER` / `MISSING_MEMBER` / `NO_MEMBERS`. Anything but
   `RESOLVABLE` means `POST /generate` and `/resolve` will 404 the combination, so an admin
   sees the problem *before* running.
2. **`POST /profiles/combinations/{id}/resolve`** — runs the **same `ProfileResolver`** the
   scheduler uses and returns the merged `ResolvedProfile` for manual preview:
   `combination_id`, `source_profile_ids`, `params` (already weight-merged), `resources`
   keyed by resource type, and `hard_constraints` / `soft_constraints` rows. A missing,
   empty, or archived-member combination is a 404, matching generation-time behaviour.

Schemas (`app/schemas/profiles.py`): `ProfileCombinationMemberResponse`,
`ProfileCombinationListResponse`, `ResolvedConstraint`,
`ProfileCombinationResolveResponse`.

**Route-ordering gotcha (the one real bug):** `GET /profiles/combinations` is registered
**before** `GET /profiles/{id}`. Starlette path params match *any single segment*, so a
literal `"combinations"` route declared later is shadowed by the `{id}` route and returns
422 (`int_parsing`). This is documented in a code comment and architecture §4.2. The
existing `POST /profiles/combine` never hit this because there is no `POST /profiles/{id}`
route. Keep this in mind for any future literal sub-route under `/profiles`.

Tests — **7 new (94 → 101)** in `app/tests/test_combinations.py` (registered in
`app/tests/__main__.py`): list returns member names/weights + RESOLVABLE; archiving a
member flips the status to INACTIVE_MEMBER; resolve shows weighted param collisions
(higher-weight member wins), unioned resources, merged member constraints; resolve output
matches what a combination generation actually schedules; unknown/archived combinations
404; empty DB → empty list. No `conftest.py` change needed — the routes live in
`app.router.profiles`, which was already in the patch loop.

Commits (one per concern): API (schemas+router), tests, docs. While updating docs the
stale Alembic chain header in the architecture doc (§3 + §9) was corrected to head
`b4f1c9d3e7a2` (the previous session committed the `variation` migration but never bumped
the chain) and the "21 tables" count in progress.md was fixed to 22.

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, architecture notes, commit rules.
- `documentation/timetable-generator-architecture.md` — **§6.2 (Combining Profiles — now
  includes the list/resolve endpoints)**, §4.2 (Profile Management endpoints), §5.1 step 4
  (scheduler `_solve`), §3 (schema incl. `variation` column + migration chain).
- `documentation/plan.md` (Phase 2 item "Profile Combination Resolution" now fully ticked)
  and `documentation/progress.md` (🟠 → next items below).
- Engine plumbing: `app/engine/profile_resolver.py` (`ProfileResolver`, `ResolvedProfile`,
  merge semantics — the resolve endpoint is a thin HTTP wrapper over it),
  `app/router/profiles.py` (new combination routes + the route-ordering comment),
  `app/schemas/profiles.py` (new combination schemas).
- Tests: `app/tests/test_combinations.py` (new), `app/tests/__main__.py` (module
  registered), `app/tests/conftest.py` (patch loop — no change needed).

## NEXT TASK — flexibility roadmap (engine-spanning)

The other option from the previous handoff is still open, and it is the top-ranked
remaining item:

1. **Flexibility roadmap** (progress.md 🟠, plan.md lines ~25-30): fold the core structural
   checks into the constraint registry (currently inline in `ConstraintChecker` — double
   booking / capacity / room-type / availability / blackouts / faculty load / published
   conflicts), generic resource requirements (replace `Subject.requires_lab` with declared
   requirements matched against room attributes), `CUSTOM` enum escape hatches for
   `RoomType`/`SessionType`/`GroupType`/`TimetableType`, and wire
   `enable_lab_batches`/`enable_soft_constraint_scoring` flags. This is larger and
   engine-spanning — worth its own session.

Further down (progress.md): **Redis Integration** (cache frequent GETs, rate-limit,
generation-conflict locking — Redis already runs as the Celery broker/backend),
**Email Notifications on Publish**, **API Polish** (pagination, error middleware, audit),
then **Phase 4 frontend + full-stack Dockerization**.

## Remaining known items (see `documentation/progress.md`)

- **Flexibility roadmap** — fold structural checks into the registry, generic resource
  requirements, `CUSTOM` enum escape hatches, wire `enable_lab_batches`.
- **Redis Integration** — caching/rate-limiting/generation-conflict-locking usage still open.
- **Email Notifications on Publish** — SMTP, faculty/HOD/incharge mail on publish.
- **API Polish** — pagination, global error middleware, request logging/audit, `/api/v1/`.
- **Frontend + full-stack Dockerization** — Next.js app + top-level compose.

## Gotchas

- Postgres runs on host port **5433** (`.env` sets `DB_PORT=5433`); Redis maps `6379`.
  Alembic head: `b4f1c9d3e7a2`. 22 tables.
- Tests: `uv run python -m app.tests` (not pytest). Add any router touched by tests to the
  patch loop in `app/tests/conftest.py`. New test modules must be imported in
  `app/tests/__main__.py` to register their suites.
- **Literal sub-routes under `/profiles` must be registered before `/{id}`** (Starlette
  path params match any single segment → a later `"combinations"` list route gets shadowed
  and returns 422). See the comment above `get_profile_combinations`.
- **Alembic enum migration gotcha:** the `variationmode` migration explicitly creates the
  enum via `variationmode.create(op.get_bind())` in `upgrade()` and drops it with
  `DROP TYPE IF EXISTS` in `downgrade()` — a bare `sa.Enum(...)` column without that call
  fails on Postgres with `type "variationmode" does not exist`. Follow the same pattern for
  any future enum column.
- **Variation semantics:** instance #1 is the deterministic baseline (seed `None`) unless
  `variation="best"`; gap criteria only reshape *seeded* re-rolls; the Hamming-distance gate
  runs in all modes. Keep `PLACEMENT_WEIGHT` strictly above any variation term so placements
  are never traded away.
- **Async mode is off by default** (`ASYNC_GENERATION=false`). Worker task tests call
  `run_generation(run_id)` directly; the async HTTP branch uses
  `celery.current_app.conf.task_always_eager = True`.
- **The auth gate is global**: tests that call a non-exempt route must pass
  `auth_headers(login_token(client))`. Only `/health` and `/auth/*` are exempt.
- The solver constructors take a `ResolvedProfile`, not `profile_id` — build one via
  `ProfileResolver(db).resolve(profile_id, combination_id)` if you construct solvers
  directly outside the scheduler.
- **Exam specifics:** `EXAM_DATE_SEPARATION` only matters with `term_start`; the single-week
  template means a 5-day week holds at most 3 exams at `min_days=2`; OR-Tools models the rule
  relationally (§5.2) and the final full-checker pass remains the safety net for other
  committed-dependent registry rules.
- `_check_cross_dept_cap` counts committed *slots* (a committed lab block contributes its
  length); the CP-SAT soft objective builders key placements by a block's **start slot**
  only.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md` checkboxes.
