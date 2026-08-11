# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

**Design decisions live in `documentation/design-decisions.md`** (a permanent ADR log — not
here). The OPEN items below are copied from it; resolve them and mark them done in the log.

## Session summary (committed & pushed)

State at handoff: **164/164 tests passing** (`uv run python -m app.tests`), frontend builds
(`npm run build`), tree clean. This session was **backend saleability hardening** (the user is
planning to deploy/propose this to a real college; frontend work is on hold until the backend is
proven). Commits in order:

1. **Make OR-Tools fail gracefully on an empty placement domain** (commit `784afe2`) — when every
   candidate is pruned, `PLACEMENT_WEIGHT * 0 == 0.0` (a bare float) crashed CP-SAT with
   `TypeError`; now it short-circuits and returns zero slots like greedy.
2. **Complete the soft-constraint system + make greedy pursue it** (commit `d83ee87`) —
   `AVOID_CONSECUTIVE_SAME_SUBJECT`, `DISTRIBUTE_SUBJECTS_EVENLY`, and `BALANCE_TEACHER_LOAD`
   were catalog-advertised but had no scorer and no CP-SAT builder (silent no-ops). Added all
   three to `scorer.py` and `soft_objective.py`. Bigger impact: the default greedy solver
   previously ignored soft preferences during placement (post-hoc scoring only); added a
   preference-aware (day, slot) scan so greedy leans toward morning slots / fresh days / light
   days. Verified live: with `TEACHER_PREFERS_MORNING(boundary 4)` on a whole department, greedy
   moved 102 sessions into the morning (186/288 → 288/288).
3. **Add MAX_DAILY_SUBJECTS data-driven rule** (commit `cdd1aeb`) — a common real-world college
   rule ("don't give a class 5 subjects in one day") that the engine left unlimited. Registered as
   a data-driven hard rule (config_json cap), auto-appears in `GET /constraints/types`, modelled
   relationally in OR-Tools. This is the "rules change without schema changes" story in action.
4. **Surface unplaced sessions** (commits `6ddea0a` + `7f25346`, migration `1d8688977519`) — a
   COMPLETED run that dropped sessions only `print()`ed to stdout (silent data loss). Added
   nullable `placement_warning` to `timetable_generations`; both solvers now report
   `unplaced_count` and the scheduler stamps the warning on the run, so `POST /generate` and the
   status endpoint report it.
5. **Docs** (commit `123e614`) + **override_drive.py** (commit `4ebedbe`) — architecture/plan/
   progress updated for all of the above; `scripts/override_drive.py` verifies manual-override
   revalidation live (conflicting move → 409 with the violation, no-op → 200).

The user explicitly asked for **no forced handoffs** — only commit/push when it makes sense for
git/memory. This HANDOFF is written to preserve context; the next session should *continue the
same backend-hardening thread* rather than start fresh.

## Open design decisions (from `documentation/design-decisions.md` — resolve these)

1. **DD-004 follow-up** — promote mail gating to a `CollegeSettings.mail_enabled` flag, or
   keep env-only? (Likely keep env-only until a college asks; but decide and record.)
2. **DD-003 follow-up** — do publish notifications need a retry queue / per-recipient opt-out /
   an admin `/notifications` endpoint? (Currently: log-and-drop.)
3. **DD-001 follow-up** — when RBAC lands, replace `config_json["notification_emails"]` with
   real HOD entities.
4. **DD-018 follow-up** — the four-service compose bring-up could not bind host port 3000 on the
   dev machine (occupied by an unrelated container); the frontend image itself was verified on an
   alternate port. Next session: run the full `docker compose up` on a free 3000 and confirm
   login → dashboard in a browser, then mark DD-018 `Live-verified`.
5. **DD-020 follow-up** — decide whether `scripts/` (seed + battle test) should be wired into CI or
   stay local dev tooling, and set a cadence for re-running the battle test after engine/solver
   changes. Also: the seeded dataset currently sits in the local Postgres (with some PUBLISHED
   instances from testing, which now reserve slots) — a fresh `--wipe --or-tools-smoke` reseed is
   the way back to a clean timing baseline.

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, commit rules, and the **Design decisions** rule.
- `documentation/design-decisions.md` — DD-020 is this session's entry; DD-018/DD-020 have open
  follow-ups (above).
- `scripts/seed_demo.py` — the college shape (departments, per-semester subject templates, faculty
  pools, rooms, assignments, profiles, params). Run `uv run python -m scripts.seed_demo --wipe
  --or-tools-smoke` to reseed.
- `scripts/battle_test.py` / `api_drive.py` / `async_drive.py` — how to re-run the scale tests.
- `app/services/export_service.py` — `generate_timetable_pdf` now renders one grid per group;
  `_build_grid` is the extracted per-group table builder.
- `app/engine/scorer.py` / `app/engine/soft_objective.py` — all six soft types ship scorers +
  CP-SAT builders; `app/engine/solvers/greedy_solver.py` has the preference-aware scan
  (`_preference_scan`) so greedy pursues soft preferences during placement.
- `app/engine/constraint_registry.py` — `MAX_DAILY_SUBJECTS` validator (`_max_daily_subjects`);
  `app/engine/solvers/or_tools_solver.py` models it + `EXAM_DATE_SEPARATION` relationally.
- `app/engine/scheduler.py` — stamps `placement_warning` from the solver's `unplaced_count`;
  `app/models/generation.py` + `app/schemas/generation.py` carry the field.
- `scripts/override_drive.py` — live manual-override revalidation check.
- Architecture doc **§4.1** (project tree incl. `scripts/`), **§4.2** (PDF export note, `GET /generate`,
  `placement_warning`), **§9**.

## NEXT TASK — Continue backend saleability hardening (frontend stays on hold)

The user is preparing to **deploy/propose this to a real college** and asked for **backend-only
work, no frontend** until the backend is proven. This session hardened: robustness (OR-Tools empty
domain), flexibility (all 6 soft constraints + greedy pursuit), the rules-change story
(`MAX_DAILY_SUBJECTS` demonstrates adding a data-driven rule with zero schema changes), and
visibility (`placement_warning`). Remaining backend gaps in rough priority:

1. **More data-driven rules colleges actually ask for** — the registry makes adding one cheap and
   it appears in `GET /constraints/types` automatically. Strong candidates: `MIN_FREE_SLOTS_PER_DAY`
   (guarantee a minimum number of free slots per group), `MAX_CONSECUTIVE_SAME_GROUP` (cap a group's
   back-to-back slots), `MAX_DAILY_HOURS` variants. Each needs a validator + catalog entry +
   relational OR-Tools model (if committed-dependent) + test + docs.
2. **`GET /instances/{id}/conflicts`** — the doc lists it as a gap; useful for a college to inspect
   where an instance is tight.
3. **`hard_violations` honesty** — it's declared but always 0 (the checker rejects invalid
   placements, so committed slots genuinely have none). Either compute a real value or document that
   it's structural-zero.
4. **EVENT/EXAM/CUSTOM scope branches** — they reuse the DEPARTMENT path today.
5. **RBAC** — deferred by the user (a later milestone; DD-001 follow-up depends on it).

When the user says the backend is done, the frontend tracks are: (a) restyle toward their reference
UI (dark sidebar + accent vs editorial light — **ask which**), (b) the Generation & Instance Viewer.

## Remaining known items (see `documentation/progress.md`)

- **Frontend depth** — shipped: Auth + Dashboard + Resource CRUD. Remaining (plan.md Phase 4):
  CSV upload modals, Master Assignment Grid, Profile & Constraint Builder, Generation Viewer
  (side-by-side grid + progress), Instance Editor (slot override UI). Plus the restyle above.
- **README & Docs, Historical Data Import, ML Preference Learning**.
- **Notification service extras** — no `/notifications` endpoint, no per-recipient opt-out,
  no retry queue, no WebSocket/SSE push.
- **Minor engine gaps** (§9 Partial) — `ScopeType` EVENT/EXAM/CUSTOM reuse the DEPARTMENT solver
  path; `SEMESTER` reset is accepted but a no-op; no `DELETE /instances/{id}/slots/...`,
  no `GET /instances/{id}/conflicts`; WebSocket progress push for async runs.

## MINI-PLAN for the next session (frontend restyle + viewer)

Follow the repo's standing workflow (commit per concern; docs in sync; record ADR entries).

1. **Restyle (if user picks a direction).** Confirm the chosen aesthetic (dark sidebar + accent, or
   editorial light) via a quick question. Then: extend `tailwind.config.ts` (colors, fonts, shadows),
   update `globals.css`, `Navbar.tsx` (→ sidebar if dark choice), `ProtectedShell`, and the shared
   `DataTable`/`Modal`/`ResourceTable` so all four CRUD pages inherit the new look. Keep it one
   commit per file group (theme / components / pages).
2. **Generation Viewer.** Add `src/app/(protected)/generate/page.tsx` (or `/runs`) with a trigger
   form + recent-runs table (reuse the dashboard's `GET /generate` list). Then an instance viewer
   at `src/app/instances/[id]/page.tsx` rendering a slots grid (day x slot) fetched from
   `GET /api/v1/instances/{id}/slots`, with a status poll loop for async runs. Reuse the new API
   `run_duration_ms` in the UI. New API types in `src/lib/types.ts`; helpers in `src/lib/api.ts`.
3. **Backend gaps, if any.** `GET /instances/{id}/slots` exists. If the viewer needs instance
   selection/publish buttons those exist too (`POST /instances/{id}/select|publish`). Avoid new
   backend surface unless genuinely needed — add + test + document it in the same change if so.
4. **Keep everything green.** `uv run python -m app.tests` (currently 154) and `npm run build` in
   `frontend/`. A live backend (`uv run uvicorn app.main:app --port 8000`) against the seeded data
   makes the viewer demo-able immediately.
5. **Docs.** Update architecture §4.1 (new pages), §4.2 if endpoints changed, §9 checkboxes;
   `plan.md`/`progress.md`. Record design decisions (e.g. the chosen visual direction as a DD; grid
   rendering approach).
6. **Commit & push**, then overwrite this HANDOFF with the new session summary + a fresh mini-plan
   for the *next* item.

## Gotchas

- Postgres runs on host port **5433** (`.env` sets `DB_PORT=5433`); Redis maps `6379`.
  Alembic head: **`f5a1b3c8e6d2`** (adds nullable `student_groups.incharge_email`). 22 tables.
- **Design decisions are tracked in `documentation/design-decisions.md`, not in this file.**
  Every new choice (or "considered and rejected") gets a DD-NNN entry in the same commit; the
  HANDOFF must copy the OPEN items verbatim so they get resolved. Keep OPEN items few.
- **New `Settings` fields must go in `.env.example` in the same commit** (real past miss —
  Redis and SMTP flags shipped without it; both fixed). The frontend has its own
  `frontend/.env.example` for `NEXT_PUBLIC_API_URL`.
- **Tests: `uv run python -m app.tests`** (not pytest). Add any router touched by tests to the
  patch loop in `app/tests/conftest.py`. New test modules must be imported in
  `app/tests/__main__.py`. **No *external* Redis/Celery/SMTP in tests** — stub or fake anything
  that would touch the network; the live-delivery email tests use an in-process loopback SMTP
  server (`socketserver`), which is local.
- **Redis and email are inert in tests by default**: `conftest.py` sets `REDIS_ENABLED=False`
  and `EMAIL_ENABLED=False`. A test that needs either enables it and MUST restore the shared
  `app.config.settings` attributes (and any module attribute) in `finally`.
- **The frontend has no backend test entry** — it's a separate npm project. Verify with
  `npm run build` (type-check + prod build) and a live backend; the SQLite suite stays backend-only.
- **The mailer's only network touch is `mail_service._deliver`** — composition tests patch
  `_deliver`; when running the real background thread, keep the patch alive until the thread
  is joined (see `test_email_notifications.py`).
- **The publish endpoint never fails on mail**: the router guards
  `dispatch_publish_notifications` and the dispatch only spawns a daemon thread. Keep it that
  way.
- **The lock is resource-keyed, not run-keyed**: overlapping resource sets are serialised; a
  busy lock FAILs the second run (409 sync / FAILED row async) — it does not queue.
- **Literal sub-routes under `/profiles` must be registered before `/{id}`** (Starlette path
  params match any single segment — a later `"combinations"` list route gets shadowed and
  returns 422). See the comment above `get_profile_combinations`.
- **Native Postgres enum migration gotcha:** `roomtype`/`sessiontype` can only be extended
  with `ALTER TYPE ... ADD VALUE` inside `upgrade()` — never drop/recreate. `d7a3c5e9f1b2`
  is the pattern; `downgrade()` is a documented no-op.
- **Structural rules are always-on**: the 14 `STRUCTURAL_RULES` run regardless of profile
  `hard_constraints` rows; a row of a structural type is decorative. New *data-driven* rules
  must be registered with `@hard_rule` AND added to `HARD_CONSTRAINT_TYPES` (the
  `GET /constraints/types` catalog test asserts exact enum ↔ list parity).
- **`requirements_json` semantics:** an empty dict means "no constraints" even with
  `requires_lab=True`; a missing `features` tag is unsatisfiable unless the room carries it in
  `equipment_json`; a subject whose requirements match no profile room schedules zero sessions.
- **Async mode is off by default** (`ASYNC_GENERATION=false`). Worker task tests call
  `run_generation(run_id)` directly; the async HTTP branch uses
  `celery.current_app.conf.task_always_eager = True`. The generation lock applies in both
  modes. For a real worker run: start with `ASYNC_GENERATION=true` and a celery worker
  (`uv run celery -A app.worker:celery_app worker`) — `scripts/async_drive.py` demonstrates this.
- **The auth gate is global**: tests that call a non-exempt route must pass
  `auth_headers(login_token(client))`. Only `/health` and `/auth/*` are exempt. **`/api/v1/*`
  is NOT exempt** — versioned routes require the same token. The frontend login page posts to
  the root `/auth/login` (the only non-versioned path the client calls).
- **Error envelope:** every error returns `{"detail": ...}`; 422 and 500 add `request_id`.
  HTTPException keeps the default shape. The frontend `api.ts` surfaces `detail` as the message.
- **Variation semantics:** instance #1 is the deterministic baseline (seed `None`) unless
  `variation="best"`; gap criteria only reshape *seeded* re-rolls; keep `PLACEMENT_WEIGHT`
  strictly above any soft/variation term.
- **Exam specifics:** `EXAM_DATE_SEPARATION` only matters with `term_start`; OR-Tools models
  the rule relationally (§5.2) and the final full-checker pass is the safety net.
- **The dockerized frontend** needs `HOSTNAME=0.0.0.0` + `PORT=3000` env (Next standalone
  binds to `$HOSTNAME`, which Docker auto-sets to an unresolvable container id) — already in
  `docker-compose.yml`.
- **Scale testing lives in `scripts/`, not `app/tests/`** (DD-020): the SQLite suite must stay
  fast and needs no Postgres. To re-baseline timing after a seed, run
  `uv run python -m scripts.seed_demo --wipe` first (the local DB currently holds PUBLISHED
  instances from testing, which reserve slots and would skew fresh runs).
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md` checkboxes.
