# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

## Session summary (committed & pushed)

State at handoff: **57/57 tests passing** (`uv run python -m app.tests`), tree clean.

This session implemented **profile combination resolution** — the "NEXT TASK" from the
previous handoff (also `documentation/progress.md` → "Newly Identified").

**The bug:** `POST /profiles/combine` stored members in `profile_combination_members`, but
`Scheduler.run()` only read `profile_id`, so `POST /generate` with a `combination_id`
failed. Now fixed end to end:

1. **`app/engine/profile_resolver.py`** (new) — `ProfileResolver.resolve(profile_id,
   combination_id)` returns a `ResolvedProfile` (params dict, resources keyed by
   `ResourceType`, hard/soft constraint lists). Merge semantics (documented in
   architecture §6.2):
   - **Resources** — union across members, de-dup by `(resource_type, resource_id)`.
   - **Parameters** — highest-weight member wins on `param_key` collisions; ties break on
     lower profile id for determinism. Values are type-cast (same casting the solver's
     old `_load_params` did).
   - **Hard constraints** — union of global rows (`profile_id IS NULL`) + every member's
     rows, de-duped by `(constraint_type, config_json)`.
   - **Soft constraints** — same union, de-duped by `(constraint_type, config_json)` with
     the highest weight kept.
   - Resolution is **in-memory per run** — no synthetic `timetable_profiles` row is
     written, so member edits are always reflected and the profiles table stays clean.
2. **Engine** — `Scheduler.run()` resolves once up front and passes the `ResolvedProfile`
   to the solvers; `GreedySolver`/`ORToolsSolver` constructors now take `profile:
   ResolvedProfile` (not `profile_id`) and read params/resources/hard/soft from it instead
   of re-querying by id. A combination generation records `profile_id=NULL` +
   `combination_id=<id>`. Missing/inactive profile or combination member → `ValueError`
   → the router returns 404.
3. **`POST /profiles/combine`** — now validates member profiles exist (404) and that a
   `weights` list matches `profile_ids` length (422).
4. **`PATCH /instances/{id}/slots/{slot_id}`** — `_revalidate_slot` re-resolves the
   generation's `combination_id` through `ProfileResolver` (with `require_active=False`
   so an override still works after a member was archived).

Commits (pushed to `main`): `0558340` (engine), `5b5bc55` (router), `88e03bb` (tests),
`a384a70` (docs).

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, architecture notes, commit rules.
- `documentation/timetable-generator-architecture.md` — schema §3, endpoints §4, engine §5,
  §6.2 (combination merge semantics — rewritten this session), parameters §8 (esp. §8.8).
- `documentation/plan.md` (phased roadmap) and `documentation/progress.md` (status).
- Engine: `app/engine/profile_resolver.py` (new), `app/engine/scheduler.py`,
  `app/engine/solvers/greedy_solver.py`, `app/engine/solvers/or_tools_solver.py`,
  `app/engine/constraint_checker.py`, `app/engine/constraint_registry.py`,
  `app/engine/scorer.py`, `app/engine/soft_objective.py`.
- Tests: `app/tests/test_settings_and_assignments.py` (Phase 4 suite — combination
  resolution), `seed_two_profiles` in `app/tests/test_runner.py`. Hand-rolled, **not** pytest.

## NEXT TASK — read-route auth consistency (product decision)

**The gap:** `GET /settings` requires a JWT (`Depends(get_current_admin)`), but most other
GETs (`/rooms`, `/faculty`, `/groups`, `/subjects`, `/profiles`, `/constraints/types`,
`/export/...`, `/history`, etc.) are public. `documentation/progress.md` → "Newly
Identified" flags this as the next item.

**Decision needed — protect everything except `/health` + `/auth/*`, or leave reads public?**

The likely direction (per the previous handoff) is **fully authenticated**: gate every
route behind `get_current_admin` except `/health` and the `/auth/register` + `/auth/login`
endpoints. That means:

- Sweeping every router in `app/router/` (and the ones auto-mounted in `app/main.py`)
  to add `current_admin: Admin = Depends(get_current_admin)` to each GET.
- A cleaner alternative: a global middleware/dependency in `app/main.py` that exempts
  only `/health` and `/auth/*` (all non-mutating + mutating auth endpoints), so individual
  routers don't each need the dependency.
- **Tests will break**: many tests GET without headers (`/health` is fine to stay public,
  but `GET /constraints/types`, `GET /rooms/` with pagination, `/export/...` reads, etc.
  will start returning 401). `app/tests/test_settings_and_assignments.py` has several
  unauthenticated GETs that would need `auth_headers(login_token(client))`.

Pick a direction, implement, update the affected tests, and document the decision in the
architecture doc §4.2 (which currently says "list/get endpoints on resources are public by
default").

## Remaining known items (see `documentation/progress.md`)

- **Registry rules** — `HOLIDAY_CALENDAR` (date-matching validator; the
  `term_start`/`slot_date` machinery is the foundation), `CONTIGUOUS_LAB_SLOTS`
  (multi-slot sessions — deep engine change), `EXAM_DATE_SEPARATION`.
- **Async generation** — Celery/Redis; `GET /generate/{id}/status` already exists.
- **OR-Tools diversity** — objective-based variation (best / minimize-teacher-gaps /
  minimize-student-gaps).
- **Flexibility roadmap** — fold structural checks into the registry, generic resource
  requirements, `CUSTOM` enum escape hatches, wire `enable_lab_batches`.
- **Frontend + full-stack Dockerization** — Next.js app + top-level compose.
- **`/profiles/combinations` router** — there is still no list endpoint and no explicit
  `POST /profiles/combinations/{id}/resolve` (resolution is automatic inside the scheduler);
  tracked in `plan.md`.

## Gotchas

- Postgres runs on host port **5433** (`.env` sets `DB_PORT=5433`); `docker/docker-compose.yml` maps it.
- Tests: `uv run python -m app.tests` (not pytest). Add any router touched by tests to the
  patch loop in `app/tests/conftest.py`.
- The solver constructors now take a `ResolvedProfile`, not `profile_id` — build one via
  `ProfileResolver(db).resolve(profile_id, combination_id)` if you construct solvers
  directly outside the scheduler.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8).
- Alembic head: `e9f4a2b6d8c0`. 22 tables. No migration was needed this session.
