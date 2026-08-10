# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

## Session summary (committed & pushed)

State at handoff: **125/125 tests passing** (`uv run python -m app.tests`), tree clean.

This session shipped **Redis Integration** (the top-ranked NEXT TASK from the previous
handoff). All three open usages from progress.md are now implemented through one optional
client, `app/services/redis_client.py`, which degrades gracefully when Redis is disabled or
unreachable (no caching / no rate limiting / unlocked generation — never a 500):

1. **Generation-conflict locking** (commit `41fd7c2`) — `Scheduler.solve_generation()`
   acquires `timetable:lock:generate:<sorted resource ids>` (the union of the resolved
   profile/combination's room/faculty/group/subject ids) before solving. Two concurrent
   runs over the same resources previously each computed their own empty published-
   reservation set and could double-book. A busy lock marks the run `FAILED` with
   `error_log` and the sync router returns **409** (`GenerationLockError` in
   `app/engine/scheduler.py`); Redis down/disabled degrades to running unlocked. Lock TTL
   600s, `release_lock` is a Lua compare-and-delete.
2. **Response caching** (commit `b1681a0`) — `GET /rooms/`, `/subjects/`, `/profiles/`,
   `/settings/` cache their serialized JSON under `timetable:cache:<collection>:<query
   params>` for 60s; paginated hits restore the `X-Total-Count` header. Every matching
   write busts the whole collection prefix.
3. **Auth rate limiting** (commit `474dfcf`) — `/auth/login` (5/min) and `/auth/register`
   (3/min) run a fixed-window counter per client IP → **429** when over. Inert without
   Redis.

**Config** — `app/config.py` gained `REDIS_URL` (default `redis://localhost:6379/0`) and
`REDIS_ENABLED` (default `True`). The handoff's original suggestion to key everything off
`ASYNC_GENERATION=false` was deliberately **not** followed: rate limiting and caching are
useful regardless of async generation, so they get their own flag.

**Tests** — **11 new (114 → 125)** in `app/tests/test_redis_integration.py` (registered in
`app/tests/__main__.py`). The suite has no Redis: `REDIS_ENABLED` is forced off in
`conftest.py`, and tests substitute a dict-backed `_FakeRedis` by monkeypatching
`redis_client._get_client`. Coverage: lock acquire/release round-trips; a busy lock marks
the run FAILED + `GenerationLockError`; HTTP 409 on a locked `POST /generate`; a downed
Redis degrades to an unlocked solve (COMPLETED); room/settings cache serve + write-busting
(stale list served after a direct DB insert, fresh after a router write); the fixed-window
rate limiter (unit + 429 over HTTP).

**Commits (in order):** `50d492f` (redis client + config), `41fd7c2` (lock engine + 409),
`b1681a0` (caching), `474dfcf` (rate limiting), `f11511b` (tests), `d3d7f06` (docs).

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, commit rules.
- `app/services/redis_client.py` — the optional client: `acquire_lock`/`release_lock`
  (tri-state: `Lock` / `False` busy / `None` unavailable), `cache_get/set(_json)`,
  `cache_delete_prefix`, `cacheable_list`/`cache_serve_list`, `check_rate_limit`.
- `app/engine/scheduler.py` — `solve_generation` lock wiring, `_acquire_resource_lock`,
  `GenerationLockError`.
- `app/router/generate.py` (409), `app/router/auth.py` (`_rate_limit` dependency),
  `app/router/rooms.py` / `subjects.py` / `profiles.py` / `settings.py` (cache pattern:
  `_<COLLECTION>_CACHE_PREFIX`, `cache_serve_list` on hit, `cacheable_list` on miss, bust
  on every write).
- `app/tests/test_redis_integration.py` — the `_FakeRedis` + `_fake_redis()`/
  `_restore_get_client()` helpers, plus `conftest.py`'s `REDIS_ENABLED=False`.
- Architecture doc **§7.9 (Redis-backed Infrastructure)** and the endpoint notes in §4.2.

## NEXT TASK — Redis Integration is DONE. Next up: **Email Notifications on Publish**

The remaining roadmap items in priority order (details in `documentation/progress.md`):

1. **Email Notifications on Publish** — SMTP + mail to faculty (personal PDF), HOD
   (summary), class incharges on `POST /instances/{id}/publish`. The export layer already
   produces per-faculty PDFs (`/export/instances/{id}/pdf?faculty_id=`), so the PDF
   attachment path exists; the mailer is the new piece.
2. **API Polish** — pagination completeness, global error middleware, request
   logging/audit, API versioning (`/api/v1/`). (Global auth gate + observability
   middleware are done.)
3. **Frontend (Next.js/React) + full-stack Dockerization** — the planned UI
   (`documentation/plan.md` Phase 4 + progress.md 🟢) plus a top-level compose running
   App + Frontend + PostgreSQL + Redis.
4. **Final polish** — README/setup guide, historical data import, ML preference learning
   (Phase 2, from manual overrides).

## Remaining known items (see `documentation/progress.md`)

- **Email Notifications on Publish** — SMTP, faculty/HOD/incharge mail on publish.
- **API Polish** — pagination, global error middleware, request logging/audit, `/api/v1/`.
- **Frontend + full-stack Dockerization** — Next.js app + top-level compose.
- **README & Docs, Historical Data Import, ML Preference Learning**.
- **`TimetableType` still lacks a `CUSTOM` label** — roadmap levers 3/4 added `CUSTOM` to
  `RoomType`/`SessionType` (the types the solver branches on); `timetable_generations.timetable_type`
  is still `CLASS | FACULTY | ROOM | EVENT | EXAM | IP` (native enum). Add `CUSTOM` the same
  way as `d7a3c5e9f1b2` if a caller needs a free-form timetable kind.

## MINI-PLAN for the next session (Email Notifications on Publish)

Follow exactly; commit per concern (engine / API / tests / docs separate).

1. **Scope it.** Read `app/router/instances.py` (`publish_instance`), the export service
   (`app/services/export_service.py` — per-faculty PDF + CSV/iCal), and the models for
   faculty email/HOD/class-incharget contact fields. Decide the mail flow: what goes to whom,
   when (trigger on publish), and how attachments are produced. Recommendation: a
   `MailService` (`app/services/mail_service.py`) that sends on publish — faculty get their
   personal PDF, HOD/class incharge a summary — and is **inert when SMTP is unconfigured**
   (like the Redis client's graceful degradation; the test suite has no SMTP server).
2. **Config.** Add `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM` (and a
   master `EMAIL_ENABLED`) to `app/config.py`; empty/unset → mailer is a no-op. Consider a
   `mail_enabled` flag on `CollegeSettings` too.
3. **Build the mailer.** Compose HTML/summary bodies + attach the per-faculty PDF
   (reuse `get_filtered_slots`/PDF rendering). Do NOT block the publish request on SMTP —
   send best-effort in a background thread or the Celery worker, and log failures.
4. **Wire into publish.** `POST /instances/{id}/publish` triggers the notifications after
   the instance is published. Never break the publish on mail failure.
5. **Tests.** New `app/tests/test_email_notifications.py` (register in `__main__.py`).
   Mock the mailer / SMTP client so the suite needs no network; assert the right
   recipients get the right payloads (faculty → personal PDF, HOD → summary) and that an
   unconfigured SMTP degrades to no-op without erroring the publish. Run `uv run python -m
   app.tests` — must stay 125/125 + new.
6. **Docs.** Architecture §4.2 (publish endpoint note), a new §7.x (notifications), §8
   config flags, and `plan.md`/`progress.md` checkboxes in the same change.
7. **Commit & push**, then overwrite this HANDOFF with the new session summary + a fresh
   mini-plan for the *next* item.

## Gotchas

- Postgres runs on host port **5433** (`.env` sets `DB_PORT=5433`); Redis maps `6379`.
  Alembic head: `d7a3c5e9f1b2`. 22 tables.
- Tests: `uv run python -m app.tests` (not pytest). Add any router touched by tests to the
  patch loop in `app/tests/conftest.py`. New test modules must be imported in
  `app/tests/__main__.py` to register their suites. **No Redis/Celery/SMTP in tests** —
  stub or fake anything network-dependent.
- **Redis in tests is inert by default**: `conftest.py` sets `REDIS_ENABLED=False`. A test
  that needs a live client assigns a fake via `redis_client._get_client` (see
  `test_redis_integration.py`) and MUST restore it in `finally`, or later tests see stale
  module state.
- **The lock is resource-keyed, not run-keyed**: two generations with disjoint resource
  sets run concurrently; overlapping sets are serialised. A busy lock marks the *second*
  run FAILED (409 sync / FAILED row async) — it does not queue.
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
  `celery.current_app.conf.task_always_eager = True`. The generation lock applies in both
  modes because it lives in `solve_generation`.
- **The auth gate is global**: tests that call a non-exempt route must pass
  `auth_headers(login_token(client))`. Only `/health` and `/auth/*` are exempt. The new
  auth rate limits are inert in tests (Redis off) but still apply via `request.client.host`
  when a fake client is installed — restore it after the test.
- **Variation semantics:** instance #1 is the deterministic baseline (seed `None`) unless
  `variation="best"`; gap criteria only reshape *seeded* re-rolls; keep `PLACEMENT_WEIGHT`
  strictly above any soft/variation term so placements are never traded away.
- **Exam specifics:** `EXAM_DATE_SEPARATION` only matters with `term_start`; OR-Tools models
  the rule relationally (§5.2) and the final full-checker pass is the safety net for other
  committed-dependent registry rules.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md` checkboxes.
