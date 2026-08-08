# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

## Session summary (committed & pushed)

State at handoff: **82/82 tests passing** (`uv run python -m app.tests`), tree clean.

This session implemented **`EXAM_DATE_SEPARATION`** — the last pending `ConstraintType`
catalog member (the "NEXT TASK" from the previous handoff, also `plan.md` Phase 2). The
handoff demanded a *domain decision first*; the decision (informed by the product intent
that branches/years sit exams at different times — "one may have now and the rest do
normal college things") was to **reuse the weekly-template engine** rather than add an
exam table. Exams are just `SessionType.EXAM` sessions in a separate generation run.

1. **Exam mode** — a profile whose `session_type` param is `"EXAM"` makes
   `GreedySolver._build_sessions()` expand each `subject_assignments` row into exactly
   **one** `SessionType.EXAM` session (not `weekly_hours` copies), `requires_lab=False`
   so any room qualifies. Shared by both solvers.
2. **Rule** — `_exam_date_separation` (`app/engine/constraint_registry.py`),
   config `{"min_days": int, "group_id"?: int}`. Only governs EXAM candidates carrying a
   materialized `slot_date` (from `term_start`); rejects any placement closer than
   `min_days` days to another committed exam of the same group. Inert without an anchor
   (mirrors `HOLIDAY_CALENDAR`).
3. **Branch coexistence** — `Scheduler._load_published_conflicts()` gained
   `exempt_groups`; the scheduler passes the resolved profile's `STUDENT_GROUP` ids in
   exam mode. The examing groups' own published class slots are skipped (their classes
   are suspended during exams, so their teacher/room/group are reusable), while every
   other branch's rooms/faculty stay reserved — an exam timetable can never steal a
   still-teaching branch's room or teacher. The manual-override re-validation in
   `app/router/instances.py::_revalidate_slot` mirrors the exemption.
4. **OR-Tools** — `_add_exam_separation` models the rule as a **relational** CP-SAT
   constraint (per group: ≤1 exam per calendar date, and no exams on two dates closer
   than `min_days`). This was necessary because the registry validator is
   committed-dependent, so the static domain pass can't prune it and the final pass alone
   would pack all of a group's exams onto one day and shed the rest.
5. **Tests** — 8 new (74 → 82): validator gap math + scoping, greedy exam mode (one exam
   per subject), greedy spacing (`min_days=2` → 3 of 5 in a Mon–Fri week), inert without
   `term_start`, OR-Tools exam mode (4 spaced exams), the `exempt_groups` loader unit
   test, and an end-to-end mixed scenario (publish a two-branch CLASS timetable, then an
   EXAM generation for branch A that must not reuse branch B's published room/teacher).

Commits (pushed to `main`): `94d7f85` (engine), `66b2773` (tests), `6c30f03` (docs).
No migration was needed — `EXAM_DATE_SEPARATION` was already in the `ConstraintType`
catalog and the constraint table is string-typed. Alembic head unchanged
(`e9f4a2b6d8c0`), still 22 tables.

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, architecture notes, commit rules.
- `documentation/timetable-generator-architecture.md` — §3.3 (registry table now includes
  `EXAM_DATE_SEPARATION`), §5.1 (the `exempt_groups` loader step), §5.2 (the relational
  CP-SAT exam rule), **§5.4 (new "Exam scheduling" subsection)** — read this first, §8
  (params: new `session_type`; `min_gap_between_exams` marked legacy), §8.8 (date
  anchoring), §6.2 (combination merge semantics), §4.2 / §7.4 (auth posture).
- `documentation/plan.md` and `documentation/progress.md` — "New Constraint Types" now
  reads **"7 of 7 done"**; the registry catalog is complete.
- Registry rules pattern: `app/engine/constraint_registry.py` (`hard_rule` decorator +
  `HARD_CONSTRAINT_REGISTRY`), validator signature `(candidate, committed, config, ctx)
  -> str | None`, `ConstraintChecker._check_configured` dispatch.
- Exam plumbing: `GreedySolver._is_exam_mode` / the exam branch in `_build_sessions`
  (`app/engine/solvers/greedy_solver.py`), `Scheduler._load_published_conflicts(
  exempt_groups=...)` (`app/engine/scheduler.py`), `ORToolsSolver._add_exam_separation`
  (`app/engine/solvers/or_tools_solver.py`).
- Tests: `app/tests/test_exam_date_separation.py` (new Phase 2 suite, registered in
  `app/tests/__main__.py`), `app/tests/test_runner.py`, `app/tests/conftest.py`.
  The exam suite's `_seed_exam_subjects(n, term_start=...)` builds N-subject exam
  profiles directly in the DB; `t_mixed_branches` seeds the two-branch scenario inline.

## NEXT TASK — Async generation pipeline (Plan Phase 3)

With the registry catalog complete, the top of the roadmap is **`plan.md` Phase 3 /
`progress.md` 🟠 Async Generation (Celery)**. The engine and API are already shaped for
it (`GET /generate/{run_id}/status` exists; generation rows carry `GenerationStatus`
`PENDING/RUNNING/COMPLETED/FAILED`), but `POST /generate` still blocks the HTTP request
while `Scheduler.run()` solves synchronously.

- **Scope:** Redis + Celery worker; `POST /generate` enqueues and returns
  `{status: "PENDING", run_id}` immediately; the worker runs `Scheduler.run()` and
  flips `generation_status` on completion/failure (fill `error_log` on failure — today
  the router catches exceptions into a 500, so the worker must own error handling).
- **Watch out:** the Scheduler currently commits the whole run in one transaction and the
  router stamps `run_duration_ms` afterwards; the worker version needs to set
  `run_duration_ms` itself. The SQLite test suite (`uv run python -m app.tests`) has no
  Celery/Redis, so keep `Scheduler.run()` runnable synchronously for tests (e.g. a
  `run_async` toggle or a thin enqueue wrapper the router chooses). Diversity filter,
  scoring, and cross-timetable safety all live inside `Scheduler.run()` already.
- Alternatively, the next-highest open items are **OR-Tools objective-based diversity**
  (best / minimize-teacher-gaps / minimize-student-gaps), the **flexibility roadmap**
  (fold structural checks into the registry, generic resource requirements, `CUSTOM`
  enum escape hatches, wire `enable_lab_batches`), the **`/profiles/combinations`
  router**, and the **frontend + full-stack Dockerization**.

## Remaining known items (see `documentation/progress.md`)

- **Async generation** — Celery/Redis (next, above).
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
- **Exam specifics:** `EXAM_DATE_SEPARATION` only matters with `term_start` (no anchor →
  inert, like `HOLIDAY_CALENDAR`); the single-week template means a heavy `min_days`
  schedule can leave exams unplaced (a 5-day week holds at most 3 exams at `min_days=2`);
  OR-Tools models the rule as a relational constraint (see §5.2), and the final full-checker
  pass remains the safety net for *other* committed-dependent registry rules (e.g.
  `MAX_CONSECUTIVE_SAME_TEACHER`) and can still drop placements.
- `_check_cross_dept_cap` counts committed *slots* (a committed lab block contributes its
  length); the CP-SAT soft objective builders key placements by a block's **start slot**
  only. A lab block counts as `block_length` hours against daily/weekly caps.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md` checkboxes.
- Alembic head: `e9f4a2b6d8c0`. 22 tables. No migration was needed this session.
