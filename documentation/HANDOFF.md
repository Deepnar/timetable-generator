# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

## Session summary (committed & pushed)

State at handoff: **87/87 tests passing** (`uv run python -m app.tests`), tree clean.

This session implemented **`ASYNC_GENERATION` — the Phase 3 Celery/Redis pipeline**
(the "NEXT TASK" from the previous handoff). Generation is **synchronous by default**
(no Redis required, tests unaffected) and **opt-in async** via `ASYNC_GENERATION=true`
in `.env`.

1. **Scheduler split.** `Scheduler.run()` (`app/engine/scheduler.py`) is now
   `create_generation()` (validates input, persists the PENDING row, raises 404 on a
   bad profile/combination) + `solve_generation(run_id)` (re-resolves the profile from
   the run row, solves, flips to COMPLETED/FAILED, stamps `run_duration_ms`) + `run()`
   = create + solve (the sync path). Failure handling moved **into the scheduler**: on
   exception `solve_generation` rolls back and marks the row `FAILED` with `error_log`
   + `completed_at` + `run_duration_ms`, then re-raises (sync router → 500; worker
   swallows).
2. **Worker + task.** `app/worker.py` builds the Celery app from
   `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`; `app/tasks/generation.py::run_generation`
   (`acks_late=True`, `worker_prefetch_multiplier=1`) opens its own DB session (reads
   `app.database.SessionLocal` at call time so the SQLite test override applies), marks
   RUNNING, calls `solve_generation()`, swallows exceptions (the row records failure).
   `enqueue_generation(run_id)` is the thin wrapper the router calls.
3. **Router.** `POST /generate` reads `settings.ASYNC_GENERATION`: sync → 201 COMPLETED
   (unchanged); async → `create_generation` + `enqueue_generation` + **202** with the
   PENDING snapshot taken *before* enqueue (so the response is PENDING even if the
   worker finishes instantly). On a broker outage it logs and falls back to solving
   synchronously. `GET /generate/{run_id}/status` already existed.
4. **Infra.** `docker/docker-compose.yml` gained a `redis:7-alpine` service (host port
   `6379`). Config gained `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`,
   `ASYNC_GENERATION` (default `false`); `.env.example` documents them.
5. **Tests — 5 new (82 → 87).** `app/tests/test_async_generation.py`: sync path stamps
   `run_duration_ms`, worker task completes a PENDING run (3 slots produced), worker
   marks a deleted-profile run FAILED with `error_log`, async HTTP returns 202 PENDING
   then polling sees COMPLETED (via Celery `task_always_eager=True`), async 404s on a
   bad profile immediately.

Commits: engine (`scheduler.py` split + failure handling), infra+config (celery/redis
deps, worker, task, router, docker-compose, .env.example), tests, docs (architecture
§3/§4/§5/§7.1/checklist, plan.md, progress.md, AGENTS.md). No migration needed — no
table changed. Alembic head unchanged (`e9f4a2b6d8c0`), still 22 tables.

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, architecture notes, commit rules.
- `documentation/timetable-generator-architecture.md` — **§7.1 (Async Generation —
  implemented)** — read this first, §5.1 (the `create_generation`/`solve_generation`
  split), §4.2 (Generation endpoints: 201 sync vs 202 async), §3 (schema, incl.
  `run_duration_ms` note), §8, §6.2.
- `documentation/plan.md` (Phase 3 checkboxes now ticked) and `documentation/progress.md`
  (Async Generation moved to Completed; Redis Integration still open for caching/rate-limit).
- Scheduler plumbing: `app/engine/scheduler.py` (`create_generation` / `solve_generation`
  / `_solve`), `app/worker.py`, `app/tasks/generation.py`
  (`run_generation` + `enqueue_generation`), `app/router/generate.py`
  (`_start_async_generation` + the sync/async branch), `app/config.py`
  (`ASYNC_GENERATION`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`).
- Tests: `app/tests/test_async_generation.py` (new), `app/tests/conftest.py`
  (SessionLocal patched; the task module reads `app.database.SessionLocal` at call time so
  no conftest change was needed), `app/tests/__main__.py` (new module registered).

## NEXT TASK — OR-Tools objective-based diversity (Plan Phase 3)

With async generation done, the top of the roadmap is the **diversity filter's future
work** (plan.md Phase 3 note; progress.md 🟠; architecture §5.1 step 4). Today diversity
is purely seed-based: instance #1 is the deterministic baseline and later instances are
re-rolled seeds kept only if their Hamming distance clears `_DIVERSITY_MIN_DISTANCE=1`.
There is no way to ask for "the best timetable" as instance #1 or to vary by a *criterion*.

- **Scope:** instance `variation` / `strategy` modes — e.g. `"best"`, `"random"`,
  `"minimize-teacher-gaps"`, `"minimize-student-gaps"` — per `POST /generate`. The
  **greedy** solver would vary its search order by criterion; **OR-Tools** would add a
  secondary objective term per criterion (teacher-gap / student-gap objectives) rather
  than only varying `random_seed`. `score_instance` + `soft_objective` already ship
  gap-based scorers (`MINIMIZE_STUDENT_FREE_SLOTS`; a teacher-gap scorer may need to be
  added to `app/engine/scorer.py`).
- **Watch out:** the objective must stay **strictly primary via `PLACEMENT_WEIGHT`**
  (placements first, variation second); instance #1 should remain the deterministic
  baseline unless `variation="best"` is requested; greedy's per-attempt re-seeding and
  the Hamming-distance acceptance gate must still run so accepted instances stay distinct.
  The response schema / request body (`GenerationRequest`) needs the new field, and the
  test suite asserts `POST /generate` shapes in many places — add the field as optional
  with a default to avoid breaking them.
- **Alternatives** if you prefer: the **flexibility roadmap** (fold structural checks
  into the registry, generic resource requirements, `CUSTOM` enum escape hatches, wire
  `enable_lab_batches`), the **`/profiles/combinations` router** (list endpoint +
  explicit `POST /profiles/combinations/{id}/resolve` — resolution today is automatic
  inside the scheduler), or the **frontend + full-stack Dockerization** (Next.js +
  top-level compose). See `documentation/progress.md`.

## Remaining known items (see `documentation/progress.md`)

- **OR-Tools diversity** — objective-based variation (best / minimize-teacher-gaps /
  minimize-student-gaps) — next, above.
- **Flexibility roadmap** — fold structural checks into the registry, generic resource
  requirements, `CUSTOM` enum escape hatches, wire `enable_lab_batches`.
- **`/profiles/combinations` router** — still no list endpoint and no explicit
  `POST /profiles/combinations/{id}/resolve`; tracked in `plan.md`.
- **Redis Integration** — Redis now runs in compose and is the Celery broker/backend, but
  caching/rate-limiting/generation-conflict-locking usage is still open.
- **Frontend + full-stack Dockerization** — Next.js app + top-level compose.

## Gotchas

- Postgres runs on host port **5433** (`.env` sets `DB_PORT=5433`); `docker/docker-compose.yml` maps it. Redis now maps `6379`.
- Tests: `uv run python -m app.tests` (not pytest). Add any router touched by tests to the
  patch loop in `app/tests/conftest.py`. New test modules must be imported in
  `app/tests/__main__.py` to register their suites.
- **Async mode is off by default** (`ASYNC_GENERATION=false`) so tests and sync dev flows
  never need Redis. Worker task tests call `run_generation(run_id)` directly; the async
  HTTP branch is tested with `celery.current_app.conf.task_always_eager = True` (runs the
  task inline) — the 202 body is the PENDING snapshot taken *before* enqueue, so it reads
  PENDING even though eager mode already completed the run.
- **The auth gate is global**: tests that call a non-exempt route must pass
  `auth_headers(login_token(client))`. Only `/health` and `/auth/*` are exempt.
- The solver constructors take a `ResolvedProfile`, not `profile_id` — build one via
  `ProfileResolver(db).resolve(profile_id, combination_id)` if you construct solvers
  directly outside the scheduler.
- **Exam specifics:** `EXAM_DATE_SEPARATION` only matters with `term_start` (no anchor →
  inert); the single-week template means a heavy `min_days` schedule can leave exams
  unplaced (a 5-day week holds at most 3 exams at `min_days=2`); OR-Tools models the rule
  as a relational constraint (architecture §5.2), and the final full-checker pass remains
  the safety net for other committed-dependent registry rules.
- `_check_cross_dept_cap` counts committed *slots* (a committed lab block contributes its
  length); the CP-SAT soft objective builders key placements by a block's **start slot**
  only.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md` checkboxes.
- Alembic head: `e9f4a2b6d8c0`. 22 tables. No migration was needed this session.
