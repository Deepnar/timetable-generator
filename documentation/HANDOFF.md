# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

**Design decisions live in `documentation/design-decisions.md`** (a permanent ADR log — not
here). The OPEN items below are copied from it; resolve them and mark them done in the log.

## Session summary (committed & pushed)

State at handoff: **154/154 tests passing** (`uv run python -m app.tests`), frontend builds
(`npm run build`), tree clean. This session was the **backend battle test at realistic scale**
(the pending item from the previous handoff). Commits in order:

1. **Scale seed + battle-test tooling** (commit `b50fa52`) — `scripts/` added:
   - `seed_demo.py` — seeds a 12-department college modeled on the `sample/` TCET timetables and
     syllabus PDFs: **576 subjects** (8 sems x 6, real COMP codes/names where the PDFs had them),
     **345 faculty** (~40 in COMP using real TCET names, generated for others), **192 groups**
     (2 divisions/sem), **204 rooms** (10 classrooms + 6 labs + 1 seminar per dept), **1152
     subject-assignments**, and **108 profiles** (DIVISION-scoped per dept/sem + DEPARTMENT-scoped
     per dept), wired to the real time grid (`slots_per_day=8`, `day_start_time=08:30`, lunch after
     slot 4, Mon-Sat, `term_start`).
   - `battle_test.py` — runs generations through the same `Scheduler` the API uses (greedy +
     OR-Tools, multi-instance, `--all-departments`).
   - `api_drive.py` — drives the live HTTP API: generate → status → instances → select → publish →
     csv/ical/pdf export.
   - `async_drive.py` — exercises the real Celery worker + Redis async path (202 PENDING → poll →
     COMPLETED).
2. **Two scale bugs fixed** (commit `41f9053`) — found by the battle test:
   - **PDF export 500'd at scale**: unfiltered multi-group instances (whole-department, 288 slots)
     crammed every group into one slot/day cell, so a row exceeded the page frame and ReportLab
     raised `LayoutError`. `generate_timetable_pdf` now renders **one grid per student group**
     (the per-class format the sample timetables use). Covered by a new multi-group PDF test.
   - **`GenerationResponse` omitted `run_duration_ms`** even though the model stamps it — the API
     (and the frontend dashboard) couldn't report timing. Field added.
3. **Docs** (commits `05c84e2`, `20ac133`) — **DD-020** records the scale-testing decision + findings;
   the verification-debt OPEN item is resolved (real Redis + Postgres + Celery were all exercised
   live). `progress.md`/`plan.md`/architecture mark the scale test shipped and document the
   per-group PDF behavior. `sample/` (real college documents with personal names) is now gitignored
   — the seed script embeds the extracted shape and never reads it.

**Scale findings (DD-020):**
- Greedy places **all 288 sessions** of a whole-department profile in **~4.3-4.7s** across all 12
  departments; per-semester profiles place all 36 in **<0.2s**; 3 instances x 288 in **~12.3s**.
- OR-Tools places all 36 sessions of a per-semester profile (5s CP-SAT timeout dominates);
  whole-department OR-Tools is intentionally not exercised (CP-SAT variable explosion — greedy is
  the whole-dept preview solver).
- Async path: `POST /generate` → 202 PENDING → real Celery worker → COMPLETED, 288 slots, `dur_ms`
  stamped. Generation lock: concurrent overlapping runs → one COMPLETED, one LOCKED. Cross-timetable
  safety: after publishing a department, a re-run places fewer sessions (published reservations block
  reuse, per DD-008).

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
- Architecture doc **§4.1** (project tree incl. `scripts/`), **§4.2** (PDF export note), **§9**.

## NEXT TASK — Backend is battle-tested. Next up: **Frontend restyle + the next frontend slice**

The user asked to only start frontend work once the backend was battle-tested — it now is. Two
frontend tracks (in priority order):

1. **Restyle toward the user's reference UI.** The current frontend is a generic Tailwind slate
   look (top navbar, bordered cards). The user's reference screenshots (reviewed this session via
   the vision tool) show either an *editorial light* aesthetic (white cards on gray, strong
   typographic hierarchy, shadow-separated surfaces, minimal color) or a *dark dashboard* with one
   vivid accent (left sidebar, charcoal surfaces, uppercase tracked section labels). **The user has
   not yet picked which** — ask (dark sidebar + accent vs editorial light) before restyling.
   Implementation is in `frontend/tailwind.config.ts`, `src/app/globals.css`, `src/components/*`.
2. **Next frontend slice (Generation & Instance Viewer)** — the highest-value missing UI (plan.md
   Phase 4): a "trigger generation" form (`POST /api/v1/generate/` with profile/combination select,
   timetable_type, instances, algorithm, variation), then instance list (`GET /api/v1/instances/
   {generation_id}`) and a slots grid (`GET /api/v1/instances/{instance_id}/slots`), polling
   `GET /api/v1/generate/{id}/status` for async runs. The API now reports `run_duration_ms` so the
   viewer can show timing.

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
