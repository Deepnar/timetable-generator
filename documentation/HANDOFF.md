# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

## Session summary (committed & pushed)

State at handoff: **94/94 tests passing** (`uv run python -m app.tests`), tree clean, pushed.

This session implemented **OR-Tools objective-based diversity** (the "NEXT TASK" from the
previous handoff). Instance diversity is no longer purely seed-based: `POST /generate`
now accepts a `variation` strategy and the solvers actively pursue it.

1. **New column.** `TimetableGeneration.variation` (`VariationMode`: `random` / `best` /
   `minimize-teacher-gaps` / `minimize-student-gaps`, `app/models/generation.py`), persisted
   so the async worker re-applies the same strategy the client asked for. New migration
   `b4f1c9d3e7a2` (head) creates the `variationmode` enum + NOT NULL column
   (`server_default='RANDOM'`). Alembic chain is still linear: `… → e9f4a2b6d8c0 →
   b4f1c9d3e7a2`.
2. **Request/response.** `GenerationRequest.variation` (defaults RANDOM, so existing
   callers are unaffected) + `GenerationResponse.variation`; router threads it through both
   the sync and async paths (`app/router/generate.py`).
3. **Greedy** (`app/engine/solvers/greedy_solver.py`). `_criterion_peer_attr()` maps a gap
   variation to the peer attribute (`faculty_id` / `student_group_id`); `_criterion_scan()`
   orders the (day, slot) scan so days the peer already teaches come first and slots are
   tried by distance to its existing placements; `_build_sessions` groups a peer's sessions
   together for criterion runs. Only **seeded** instances pursue the criterion — instance #1
   stays the deterministic baseline.
4. **OR-Tools** (`app/engine/solvers/or_tools_solver.py`). `_build_variation_terms()` adds a
   secondary span term to the CP-SAT objective for seeded instances with a gap variation
   (weight −1.0, far below `PLACEMENT_WEIGHT=1000.0` so placements stay strictly primary).
   The span builder was generalized in `app/engine/soft_objective.py` into
   `_build_span_terms(ctx, peer_attr, label)` shared by the student- and teacher-gap
   objectives.
5. **Teacher-gap scorer.** `MINIMIZE_TEACHER_FREE_SLOTS` added to `app/engine/scorer.py`
   (mirror of the student-gap scorer) and to the `SOFT_OBJECTIVE_REGISTRY`; documented in
   the architecture soft-constraint table (§3.3).
6. **Scheduler** (`app/engine/scheduler.py`). `_solve()` collects all `_DIVERSITY_ATTEMPTS`
   candidates per instance. For `"best"` it seeds instance #1 too, keeps only attempts
   passing the Hamming-distance gate, and takes the highest `soft_score` (first attempt if
   no soft rules are active); other modes keep the existing seed logic
   (`None` for instance #1, else `i*100+attempt`) with the last-attempt fallback.
7. **Tests — 7 new (87 → 94).** `app/tests/test_variation.py`: default + explicit variation
   echoed on run/status, async create_generation carries BEST, instance #1 baseline
   unchanged for gap modes, greedy/OR-Tools candidates actually reach 0 free slots, and BEST
   matches the independently recomputed max of seeds 0..5.

Commits (one per concern): model+migration, engine, router+schema, tests, docs.

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, architecture notes, commit rules.
- `documentation/timetable-generator-architecture.md` — **§5.3 (Diversity Filter + variation
  — implemented)** — read this first, §5.1 step 4 (scheduler `_solve`), §5.2 (CP-SAT
  objective incl. variation terms), §4.2 (Generation endpoints), §3 (schema incl. the
  `variation` column), §8.6/§8.7 (tuning + soft scoring).
- `documentation/plan.md` (Phase 2/3 items now ticked; Phase 4 = frontend) and
  `documentation/progress.md` (🟠 → next items below).
- Engine plumbing: `app/engine/scheduler.py` (`_solve`, `_make_solver`),
  `app/engine/solvers/greedy_solver.py` (`_criterion_peer_attr`, `_criterion_scan`,
  `_build_sessions`), `app/engine/solvers/or_tools_solver.py` (`_build_variation_terms`),
  `app/engine/soft_objective.py` (`_build_span_terms`), `app/engine/scorer.py`
  (`_minimize_teacher_free_slots`).
- Tests: `app/tests/test_variation.py` (new), `app/tests/conftest.py` (no change needed —
  generate router was already patched), `app/tests/__main__.py` (new module registered).

## NEXT TASK — `/profiles/combinations` router + flexibility roadmap

With variation done, pick one of these two (both are small- to medium-sized; the previous
handoff ranked them first):

1. **`/profiles/combinations` router** (`app/router/profiles.py` area; architecture §6.2 and
   §4.2, plan.md lines ~42): there is still **no list endpoint** and **no explicit
   `POST /profiles/combinations/{id}/resolve`** — resolution is automatic inside the
   scheduler via `ProfileResolver`. Add `GET /profiles/combinations` (member profiles,
   weights, resolution status) and the explicit resolve endpoint that returns the merged
   `ResolvedProfile` for manual preview/discoverability. Register the router in
   `app/main.py`; if the SQLite tests touch it, add its module to the patch loop in
   `app/tests/conftest.py`.
2. **Flexibility roadmap** (progress.md 🟠, plan.md lines ~25): fold the core structural
   checks into the constraint registry (currently inline in `ConstraintChecker`), generic
   resource requirements, `CUSTOM` enum escape hatches, and wire
   `enable_lab_batches`/`enable_soft_constraint_scoring` flags. Larger, engine-spanning —
   worth its own session.

Further down (progress.md): **Redis Integration** (cache frequent GETs, rate-limit,
generation-conflict locking — Redis already runs as the Celery broker/backend),
**Email Notifications on Publish**, **API Polish** (pagination, error middleware, audit),
then **Phase 4 frontend + full-stack Dockerization**.

## Remaining known items (see `documentation/progress.md`)

- **`/profiles/combinations` router** — no list endpoint, no explicit resolve endpoint.
- **Flexibility roadmap** — fold structural checks into the registry, generic resource
  requirements, `CUSTOM` enum escape hatches, wire `enable_lab_batches`.
- **Redis Integration** — caching/rate-limiting/generation-conflict-locking usage still open.
- **Email Notifications on Publish** — SMTP, faculty/HOD/incharge mail on publish.
- **API Polish** — pagination, global error middleware, request logging/audit, `/api/v1/`.
- **Frontend + full-stack Dockerization** — Next.js app + top-level compose.

## Gotchas

- Postgres runs on host port **5433** (`.env` sets `DB_PORT=5433`); Redis maps `6379`.
  Alembic head: `b4f1c9d3e7a2`. 22 tables (now 22 + the `variation` column).
- Tests: `uv run python -m app.tests` (not pytest). Add any router touched by tests to the
  patch loop in `app/tests/conftest.py`. New test modules must be imported in
  `app/tests/__main__.py` to register their suites.
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
