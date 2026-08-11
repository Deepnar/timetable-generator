# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

**Design decisions live in `documentation/design-decisions.md`** (a permanent ADR log — not
here). The OPEN items below are copied from it; resolve them and mark them done in the log.

## Session summary (committed & pushed)

State at handoff: **175/175 tests passing** (`uv run python -m app.tests`), frontend builds
(`npm run build`), tree clean. This session started the **frontend**: an editorial-light restyle
(user-selected direction), plus the "run it and see it" visual-verification loop the user asked
for (headless-Chrome screenshots reviewed through the vision skill). The screenshot loop surfaced
and fixed two real frontend bugs, and the backend gained a configurable CORS origins setting.
Commits in order:

0. **CORS origins configurable** (commit `d763a8f`) — the allow-list was hardcoded to
   `localhost:3000`, blocking any other dev origin; now driven by `CORS_ORIGINS` (default
   `localhost:3000,localhost:3001`), documented in `.env.example`.
1. **Editorial-light restyle + screenshot harness** (commit `ecf2d03`) — theme tokens (warm
   canvas, white shadow-separated cards, serif display headings, charcoal accents), all
   components/pages restyled, and `frontend/scripts/screenshot.mjs` (raw CDP over system Chrome,
   real login + per-page capture). Surfaced and fixed: an auth-init race (ProtectedShell briefly
   redirected to /login on navigation with a stored token) and a singularization bug
   ("facult" for Faculty).
2. **Docs** (commit `ff0ca05`) — architecture §4.1/§9, progress.md note the restyle + harness.

Prior to this session, the same thread had completed all six backend loose ends and re-verified
them at scale (`scripts/full_stack_test.py`), surfacing two more backend bugs (see the earlier
commits in the log).

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
6. **All six loose ends** (commits `ff0674e`→`f47f006`) — honest `hard_violations` (re-validated
   with the full checker); OR-Tools relational models for `MAX_CONSECUTIVE_SAME_TEACHER`
   (sliding-window CP-SAT) and confirmed `TEACHER_YEAR_RESTRICTION` was already statically
   pruned; `scope_type=EXAM` implies exam mode; wired `solver_timeout_seconds` +
   `diversity_threshold` params and added the `ALLOW_FREE_LAST_SLOT` data-driven rule; **RBAC**
   (DD-021: role column, JWT role claim, `require_roles`, `/auth/me`, admin-only `/auth/users`).
7. **Full-features-at-scale verification** (commits `dac418e`, `040ff87`, `05d92b4`) —
   `scripts/full_stack_test.py` re-verifies every capability at whole-department scale (soft
   pursuit, new rules, OR-Tools relational + fallback, honesty fields, RBAC, conflict audit,
   real Celery async path). Surfaced and fixed two real bugs: **OR-Tools returned 0 slots** on a
   big relational-rule profile when CP-SAT exceeded its budget before a first solution (now falls
   back to greedy → 288/288 instead of empty), and **duplicate admin names returned 500** (now
   409).

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
- `app/engine/scheduler.py` — stamps `placement_warning` from the solver's `unplaced_count`,
  reads `diversity_threshold`, and computes honest `hard_violations` per instance;
  `app/models/generation.py` + `app/schemas/generation.py` carry the field.
- `app/models/admin.py` + `app/utils/auth.py` + `app/router/auth.py` — RBAC (role enum, JWT role
  claim, `require_roles`, `/auth/me`, `/auth/users`); migration `48c4fc85dd73`.
- `scripts/override_drive.py` — live manual-override revalidation check.
- Architecture doc **§4.1** (project tree incl. `scripts/`), **§4.2** (PDF export note, `GET /generate`,
  `placement_warning`, `/auth/me`, `/auth/users`), **§5.4** (scope-driven exam mode), **§7.4**
  (RBAC), **§8.2/8.3/8.6/8.7**, **§9**.

## NEXT TASK — Frontend started (editorial-light restyle done). Next: the Generation & Instance Viewer.

The backend loose ends are done and verified at scale. The frontend restyle (editorial-light,
user-selected) is shipped and visually verified via the screenshot harness. The natural next
slice is the **Generation & Instance Viewer** (plan.md Phase 4):

- A "trigger generation" form (`POST /api/v1/generate/` with profile/combination select,
  timetable_type, instances, algorithm, variation).
- Instance list (`GET /api/v1/instances/{generation_id}`) and a slots grid
  (`GET /api/v1/instances/{instance_id}/slots`) — day × slot layout.
- Poll `GET /api/v1/generate/{id}/status` for async runs; surface `run_duration_ms` and
  `placement_warning`.
- Reuse the screenshot harness (`npm run screenshot` → `frontend/scripts/screenshot.mjs`) to
  visually verify each new page through the vision skill.

Also open: CSV upload modals, Master Assignment Grid, Profile & Constraint Builder, Instance
Editor (slot override UI), and the backend follow-ups (more rules, read-scoping, `/conflicts`,
notification extras). The screenshot harness currently targets `:3001` (port 3000 is occupied on
this machine by an unrelated container) — set `FRONT_URL` if the frontend runs elsewhere.

## Remaining known items (see `documentation/progress.md`)

- **Frontend depth** — shipped: Auth + Dashboard + Resource CRUD (restyled editorial-light).
  Remaining (plan.md Phase 4): CSV upload modals, Master Assignment Grid, Profile & Constraint
  Builder, Generation Viewer (side-by-side grid + progress), Instance Editor (slot override UI).
- **README & Docs, Historical Data Import, ML Preference Learning**.
- **Notification service extras** — no `/notifications` endpoint, no per-recipient opt-out,
  no retry queue, no WebSocket/SSE push.
- **Minor engine gaps** (§9 Partial) — `SEMESTER` reset is accepted but a no-op; no
  `DELETE /instances/{id}/slots/...`,
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
  Alembic head: **`48c4fc85dd73`** (adds `admins.role` for RBAC; prior `1d8688977519` added
  `placement_warning`). 22 tables.
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
