# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

**Design decisions live in `documentation/design-decisions.md`** (a permanent ADR log — not
here). The OPEN items below are copied from it; resolve them and mark them done in the log.

## Session summary (committed & pushed)

State at handoff: **152/152 tests passing** (`uv run python -m app.tests`), frontend builds
(`npm run build`), tree clean. Commits in order:

1. **`GET /generate` list endpoint** (commit `41eca0e`) — the dashboard needs a recent-runs
   view but only `POST /generate` and `GET /generate/{id}/status` existed. Added `GET /generate/`
   (newest first, `X-Total-Count` pagination via the shared `paginate()`), covered in the API
   polish suite (148 → 152 tests with the group suite below).
2. **`PUT /groups/{id}`** (commit `2747eeb`) — groups were the only resource without update
   (rooms/faculty/subjects all have PUT). Full CRUD parity so the frontend tables can offer
   edit on every entity. Reuses `StudentGroupCreate`, soft-deletes unchanged. New 4-test
   "Phase 6 — Student group CRUD" suite.
3. **Frontend scaffold** (commit `478f9c3`) — hand-rolled Next.js 14 App Router + TypeScript +
   Tailwind in `frontend/` (no create-next-app). `src/lib/api.ts` fetch client: `NEXT_PUBLIC_API_URL`
   base, Bearer JWT from localStorage, `X-Total-Count` for lists, 401 → redirect to `/login`.
   `AuthProvider`/`useAuth`, `Modal`, `DataTable`, and config-driven `ResourceTable` components.
4. **Frontend pages** (commit `5f864eb`) — `/login` (posts to `/auth/login`), `/dashboard`
   (resource counts from `X-Total-Count`, recent runs from `GET /generate`, quick-action cards),
   and `/rooms`, `/faculty`, `/groups`, `/subjects` as thin configs over `ResourceTable`
   (server pagination + filters + create/edit/delete modals). All client components behind
   `ProtectedShell`.
5. **Dockerization** (commit `41cc564`) — root `Dockerfile` (official `uv` image, syncs
   `pyproject.toml`+`uv.lock`, entrypoint runs `alembic upgrade head` then uvicorn),
   `frontend/Dockerfile` (multi-stage, Next standalone output, `NEXT_PUBLIC_API_URL` build arg),
   `.dockerignore`s, and a top-level `docker-compose.yml` running App + Frontend + PostgreSQL +
   Redis with healthchecks. `docker/docker-compose.yml` stays the backend-only dev infra.
   Verified live: both images build; the containerized API+Postgres+Redis stack served
   register → login → versioned list/create with Redis caching active; the frontend image
   served the login page on an alternate port (host :3000 was occupied by an unrelated
   open-webui container, not a compose fault).
6. **Docs** (commit `0da83cd`) — architecture §4.1 (`frontend/` tree + Dockerfile/compose),
   §4.2 (`GET /generate`, `PUT /groups/{id}`, frontend consumption note), §9 (frontend first
   slice + Dockerization → Shipped; pagination list + `generate`); `plan.md` Phase 4/6
   checkboxes; `progress.md` 🟢/🔵 checkboxes + Current State; `README.md` frontend setup +
   full-stack docker + tech-stack/layout/roadmap. ADR log: **DD-017** (Next.js 14 admin app),
   **DD-018** (top-level compose = full stack; `docker/` stays backend-only dev infra),
   **DD-019** (browser calls the API directly via `NEXT_PUBLIC_API_URL`, no Next rewrite proxy).

## Open design decisions (from `documentation/design-decisions.md` — resolve these)

1. **DD-004 follow-up** — promote mail gating to a `CollegeSettings.mail_enabled` flag, or
   keep env-only? (Likely keep env-only until a college asks; but decide and record.)
2. **DD-003 follow-up** — do publish notifications need a retry queue / per-recipient opt-out /
   an admin `/notifications` endpoint? (Currently: log-and-drop.)
3. **DD-001 follow-up** — when RBAC lands, replace `config_json["notification_emails"]` with
   real HOD entities.
4. **Verification debt** — the async/Celery and Redis paths are tested with
   fakes/`task_always_eager`; the SQLite suite forces `REDIS_ENABLED=false`. The dockerized
   stack does exercise **real Redis** (caching keys observed), but a live `python run_tests.py`
   against the dockerized app is still worth running. Decide a cadence for the live smoke test.
5. **DD-018 follow-up** — the four-service `docker compose up` could not bind host port 3000 on
   this dev machine (occupied by an unrelated container); the frontend image itself was verified
   on an alternate port. Next session: run the full `docker compose up` on a free 3000 and
   confirm login → dashboard in a browser, then mark DD-018 `Live-verified`.

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, commit rules, and the **Design decisions** rule.
- `documentation/design-decisions.md` — DD-017/018/019 are this session's entries; DD-018 has an
  open follow-up (see above).
- `frontend/src/lib/api.ts` — the fetch client (base URL, JWT, `X-Total-Count`, 401 redirect).
- `frontend/src/components/ResourceTable.tsx` — the config-driven CRUD table the four resource
  pages are built on (fields/filters/columns config).
- `frontend/src/app/dashboard/page.tsx` — counts via `limit=1` + `X-Total-Count`, recent runs
  via `GET /api/v1/generate/`.
- `docker-compose.yml` + `Dockerfile` + `docker/entrypoint.sh` + `frontend/Dockerfile` — the
  full-stack bring-up.
- Architecture doc **§4.1** (project tree incl. `frontend/`), **§4.2** (endpoint list incl.
  `GET /generate` + `PUT /groups/{id}`), **§9** (roadmap).

## NEXT TASK — Frontend first slice is DONE. Next up: **README/final polish (Phase 6)**

The remaining roadmap items in priority order (details in `documentation/progress.md`):

1. **README & final polish** — README/setup guide is largely drafted this session; finish it,
   plus code cleanup / docstrings. Also the **rest of the frontend** (Phase 4): CSV upload
   modals, the Master Assignment Grid, profile/constraint builder, and the generation/instance
   viewer with slot overrides.
2. **Historical data import** and **ML preference learning** (Phase 2, from manual overrides).
3. **Notification extras** — `/notifications` admin endpoint, per-recipient opt-out, retry queue,
   WebSocket/SSE push.

## Remaining known items (see `documentation/progress.md`)

- **Frontend depth** — shipped: Auth + Dashboard + Resource CRUD. Remaining (plan.md Phase 4):
  CSV upload modals, Master Assignment Grid, Profile & Constraint Builder, Generation Viewer
  (side-by-side grid + progress), Instance Editor (slot override UI).
- **README & Docs, Historical Data Import, ML Preference Learning**.
- **Notification service extras** — no `/notifications` endpoint, no per-recipient opt-out,
  no retry queue, no WebSocket/SSE push.
- **Minor engine gaps** (§9 Partial) — `ScopeType` EVENT/EXAM/CUSTOM reuse the DEPARTMENT
  solver path; `SEMESTER` reset is accepted but a no-op; no `DELETE /instances/{id}/slots/...`,
  no `GET /instances/{id}/conflicts`; WebSocket progress push for async runs.

## MINI-PLAN for the next session (Frontend depth or README/final polish)

Follow the repo's standing workflow (commit per concern; docs in sync; record ADR entries).

If picking up **the next frontend slice** (Generation Viewer is the highest-value missing UI):
1. **Scope it.** Read `documentation/plan.md` Phase 4 and the 🟢 remaining frontend items in
   `progress.md`. The natural next slice is the **Generation & Instance Viewer**: a "trigger
   generation" form (profile/combination select, timetable_type, instances, algorithm,
   variation) posting to `POST /api/v1/generate/`, then listing instances via
   `GET /api/v1/instances/{generation_id}` and slots via `GET /api/v1/instances/{instance_id}/slots`
   in a grid. Poll `GET /api/v1/generate/{id}/status` for async runs.
2. **Follow the existing patterns.** Reuse `ResourceTable`/`DataTable`/`Modal`; add a page under
   `src/app/(protected)/` — there is no route group today, pages each wrap themselves in
   `ProtectedShell`. New API types go in `src/lib/types.ts`; new client helpers in `src/lib/api.ts`.
3. **Backend gaps, if any.** The viewer may need `GET /instances/{id}/slots` (exists) and
   instance selection (`POST /instances/{id}/select` exists). Avoid new backend surface unless
   the UI genuinely needs it — add + test + document it in the same change if so.
4. **Keep the suite green** (`uv run python -m app.tests`, currently 152) and the frontend
   building (`npm run build` in `frontend/`).
5. **Docs.** Update architecture §4.1 (new pages), §4.2 if endpoints were added, §9 checkboxes;
   `plan.md`/`progress.md`. Record any design decision (e.g. grid rendering approach) as a DD.
6. **Commit & push**, then overwrite this HANDOFF with the new session summary + a fresh
   mini-plan for the *next* item.

If picking up **README/final polish** instead: finish the README setup guide + API examples,
do a docstring/typing pass, and close the open ADR items that are decidable without new features
(DD-004 mail gating, the verification-debt cadence).

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
  modes.
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
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md` checkboxes.
