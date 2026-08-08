# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

## Session summary (committed & pushed)

State at handoff: **58/58 tests passing** (`uv run python -m app.tests`), tree clean.

This session implemented the **read-route auth consistency** task (the "NEXT TASK" from the
previous handoff, also `documentation/progress.md` → "Newly Identified"). Product decision
made: **fully authenticated** — every route requires a valid admin JWT except `GET /health`
and the `/auth/*` endpoints.

1. **`app/main.py`** — new global `require_auth` middleware. It rejects any request without a
   valid admin JWT unless the path (trailing slash normalized) is `/health` or starts with
   `/auth/`. One middleware instead of a per-route dependency means a new router/endpoint
   cannot accidentally be left public. Registration order is deliberate: `require_auth` is
   registered first (innermost), then `observability`, then CORS last (outermost) — so a
   401 still gets logged/audited and still carries CORS headers. `/docs` and `/openapi.json`
   are now gated too.
2. **`app/utils/auth.py`** — extracted `authenticate_token(token, db) -> Admin | None`,
   shared by `get_current_admin` and the middleware so every request is checked identically
   (JWT decode → admin exists → `is_active`). `get_current_admin` still raises the 401 +
   `WWW-Authenticate: Bearer` exception on failure.
3. **Router cleanup** — dropped the now-redundant `Depends(get_current_admin)` from GETs that
   never used the admin identity (`/settings`, `/instances`, `/history`, `/reset/log`,
   `/export/*`, `/assignments`, `/audit`, `/generate/{id}/status`). It stays on every mutation
   endpoint that needs `current_admin.id` (and on `GET /profiles/...` etc. reads only via the
   middleware now). Verified no dangling imports remain.
4. **Tests** — `GET /constraints/types` now logs in first; added a "Phase 5 — Global auth
   gate" suite asserting 401 on 15 previously-public read routes without a token and 200 with
   one, while `/health` and `/auth/login` stay open.

Commits (pushed to `main`): `1db498c` (app), `7001efb` (tests), `9931ae4` (docs).

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, architecture notes, commit rules.
- `documentation/timetable-generator-architecture.md` — §4.2 (auth posture, rewritten this
  session), §7.4 (auth global, RBAC not implemented), schema §3, engine §5, §6.2
  (combination merge semantics), parameters §8.
- `documentation/plan.md` and `documentation/progress.md` — status; the "Newly Identified"
  section is now empty (read-route auth struck through).
- Auth: `app/utils/auth.py` (bcrypt direct, `authenticate_token`, `get_current_admin`),
  `app/main.py` (`require_auth` middleware + exempt paths).
- Engine: `app/engine/profile_resolver.py`, `app/engine/scheduler.py`,
  `app/engine/constraint_checker.py`, `app/engine/constraint_registry.py` (the `@hard_rule`
  decorator + `HARD_CONSTRAINT_REGISTRY`), `app/engine/solvers/*`.
- Tests: `app/tests/test_settings_and_assignments.py` (Phase 2 registry tests),
  `app/tests/test_runner.py` (`seed_minimal`, `seed_two_profiles`), `app/tests/conftest.py`.

## NEXT TASK — `HOLIDAY_CALENDAR` registry rule (date-matching validator)

The foundation is already in place: the `term_start` profile parameter materialises
`slot_date` on every committed slot (see architecture §8.8), and the availability checker
already consults date windows. `HOLIDAY_CALENDAR` just needs a **date-matching validator**:

- Add it to the `ConstraintType` enum catalog + `HARD_CONSTRAINT_TYPES` in
  `app/models/constraints.py` (so `GET /constraints/types` surfaces it automatically), and
  register a validator in `app/engine/constraint_registry.py` keyed by
  `HOLIDAY_CALENDAR`.
- Decide the `config_json` shape. Natural options: `{"holidays": ["2025-01-26", ...]}` (a
  list of ISO dates) or `{"excluded_dates": [...]}` — pick one and document it in
  architecture §3.3 + §8. A validator should reject any candidate whose `slot_date`
  (or the date derived from `day_of_week` relative to `term_start`) falls on a listed
  holiday, and be a no-op when the slot carries no materialised date.
- Wire it into both solvers like the other registry rules: greedy via `ConstraintChecker`
  (registry rules are validated on every candidate), OR-Tools via the domain-pruning pass
  (static rules like `SUBJECT_TIME_PREFERENCE`/`LAB_BATCH_ROTATION` are the template).
- Add tests: a holiday blocks that date's slots end-to-end; a holiday outside the term or a
  no-`slot_date` slot is unaffected.
- This is the first of the pending registry rules; `CONTIGUOUS_LAB_SLOTS` (multi-slot
  sessions) and `EXAM_DATE_SEPARATION` remain after it (plan.md Phase 2).

## Remaining known items (see `documentation/progress.md`)

- **Registry rules** — `HOLIDAY_CALENDAR` (next, above), `CONTIGUOUS_LAB_SLOTS` (multi-slot
  sessions — deep engine change), `EXAM_DATE_SEPARATION`.
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
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8).
- Alembic head: `e9f4a2b6d8c0`. 22 tables. No migration was needed this session.
