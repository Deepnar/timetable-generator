# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

**Design decisions live in `documentation/design-decisions.md`** (a permanent ADR log — not
here). The OPEN items below are copied from it; resolve them and mark them done in the log.

## Session summary (committed & pushed)

State at handoff: **147/147 tests passing** (`uv run python -m app.tests`), tree clean.

Shipped this session: **API Polish** (the NEXT TASK from the previous handoff). Three
commits of code + tests + docs + handoff:

1. **Pagination completeness** (commit `9c4436a`) — every top-level list endpoint now
   paginates through `app/utils/pagination.py` (`?skip=`/`?limit=`, `X-Total-Count`
   header). The gaps were `GET /profiles/`, `GET /constraints/hard`, `GET /constraints/soft`,
   `GET /history/`, `GET /blackouts/`, `GET /faculty_availability/`. `GET /profiles/` folds
   the page window into its Redis cache key and restores the total header on cache hits.
   Sub-resource lists (`/instances/{id}/slots`, `/profiles/{id}/resources`,
   `/profiles/{id}/parameters`, `/profiles/combinations`) intentionally stay unpaginated —
   they're bounded by one parent row.
2. **Global JSON error envelope** (commit `4120d73`) — every error returns the
   FastAPI-default `{"detail": ...}` shape. Two global handlers registered in `app/main.py`
   lock it and add `request_id`: `RequestValidationError` → 422 with `{"detail": errors,
   "request_id"}`, generic `Exception` → 500 with `{"detail": "Internal server error",
   "request_id"}`. HTTPException keeps the default body. The observability middleware stores
   the id on `request.state.request_id` so handlers can echo it; the middleware stays the
   safety net for exceptions raised outside the routing layer.
3. **`/api/v1` versioning** (commit `4120d73`) — one `APIRouter(prefix="/api/v1")`
   aggregator in `app/main.py` includes every router except `auth`. Unversioned routes stay
   live (existing clients + `/docs` keep working); `/health` + `/auth/*` remain root-only
   (the auth-exempt paths); both prefixes sit behind the global auth gate. Audit logs record
   the versioned path for versioned mutations.
4. **Tests** (commit `43a6e16`) — new `app/tests/test_api_polish.py`, 13 tests (134 → 147):
   each newly paginated list asserts `limit` + `X-Total-Count` (+ skip page); the error
   envelope suite uses a throwaway `/__test_unhandled__` route (added then removed) to prove
   the 500 shape, plus validation-422 and HTTPException/404/401 shapes; the versioning suite
   proves the versioned routes serve the same data behind auth, that `/api/v1` is **not**
   auth-exempt, that `/health` stays root-only, and that a versioned mutation is audited.
5. **Docs** (commit `96fc9cb`) — architecture §4.2 intro now documents versioning + the
   error envelope and marks the paginated lists; new §7.10 "API versioning & the JSON error
   envelope"; §9 shipped list updated. `plan.md`/`progress.md` check the API Polish box.
   `design-decisions.md` records **DD-014** (error envelope + rejected `{"error": ...}`),
   **DD-015** (`/api/v1` aggregator + rejected per-router prefix / `v2` param / dropping
   unversioned), **DD-016** (paginate top-level lists, keep sub-resource lists bounded).

**Commits (in order):** `9c4436a` (pagination), `4120d73` (error envelope + versioning),
`43a6e16` (tests), `96fc9cb` (docs), <handoff commit>.

## Open design decisions (from `documentation/design-decisions.md` — resolve these)

1. **DD-004 follow-up** — promote mail gating to a `CollegeSettings.mail_enabled` flag, or
   keep env-only? (Likely keep env-only until a college asks; but decide and record.)
2. **DD-003 follow-up** — do publish notifications need a retry queue / per-recipient opt-out /
   an admin `/notifications` endpoint? (Currently: log-and-drop.)
3. **DD-001 follow-up** — when RBAC lands, replace `config_json["notification_emails"]` with
   real HOD entities.
4. **Verification debt** — the async/Celery and Redis paths are tested with
   fakes/`task_always_eager`; a live Redis + live Postgres smoke test (`python run_tests.py`)
   has not been run recently. Decide a cadence for the live smoke test.

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, commit rules, and the **Design decisions** rule.
- `documentation/design-decisions.md` — DD-014/DD-015/DD-016 are this session's entries.
- `app/main.py` — the `/api/v1` aggregator, the two global exception handlers, and the
  `request.state.request_id` handoff in the observability middleware.
- `app/utils/pagination.py` — the shared `Pagination`/`pagination`/`paginate` used everywhere.
- `app/router/profiles.py::get_profiles` — the pattern for caching + pagination together.
- `app/tests/test_api_polish.py` — the pagination / error-envelope / versioning suites,
  including the throwaway-route 500 test (add then remove from `app.router.routes`).
- Architecture doc **§4.2** (endpoint listing + versioning/error notes) and **§7.10**.

## NEXT TASK — API Polish is DONE. Next up: **Frontend (Next.js/React) + full-stack Dockerization**

The remaining roadmap items in priority order (details in `documentation/progress.md`):

1. **Frontend (Next.js/React) + full-stack Dockerization** — the planned UI
   (`documentation/plan.md` Phase 4 + progress.md 🟢) plus a top-level compose running
   App + Frontend + PostgreSQL + Redis.
2. **Final polish** — README/setup guide, historical data import, ML preference learning
   (Phase 2, from manual overrides).
3. **Notification extras** (already shipped email path, §7.7) — `/notifications` admin
   endpoint, per-recipient opt-out, retry queue, WebSocket/SSE push.

## Remaining known items (see `documentation/progress.md`)

- **Frontend + full-stack Dockerization** — Next.js app + top-level compose
  (currently `docker/docker-compose.yml` runs only Postgres).
- **README & Docs, Historical Data Import, ML Preference Learning**.
- **Notification service extras** — no `/notifications` endpoint, no per-recipient opt-out,
  no retry queue, no WebSocket/SSE push.
- **Minor engine gaps** (§9 Partial) — `ScopeType` EVENT/EXAM/CUSTOM reuse the DEPARTMENT
  solver path; `SEMESTER` reset is accepted but a no-op; no `DELETE /instances/{id}/slots/...`,
  no `GET /instances/{id}/conflicts`; WebSocket progress push for async runs.

## MINI-PLAN for the next session (Frontend + Dockerization)

Follow exactly; commit per concern (frontend scaffold / app pages / compose / docs separate).

1. **Scope it.** Read `documentation/plan.md` Phase 4 and the 🟢 Frontend section of
   `progress.md`. Decide the stack: **Next.js 14+ App Router + TypeScript + Tailwind**, using
   `fetch` against the versioned API (`/api/v1`, JWT Bearer from `/auth/login`). The API has
   no CORS limit beyond `http://localhost:3000` (see `CORSMiddleware` in `app/main.py`). Pick
   the first slice (Auth + Dashboard + Resource tables) — not the whole grid builder.
2. **Scaffold.** Create `frontend/` in the repo with `npx create-next-app` (or a hand-rolled
   minimal app if that's cleaner for the monorepo), a `.env` for `NEXT_PUBLIC_API_URL`, and a
   small API client module that attaches the JWT. Keep it runnable with `npm run dev`.
3. **Dockerization.** A **top-level** `docker-compose.yml` (or extend `docker/docker-compose.yml`)
   that runs App + Frontend + PostgreSQL + Redis together; `frontend/Dockerfile` + the app's
   Dockerfile. Wire the ports so `docker compose up` gives a working login → dashboard.
   **Decide and record in `design-decisions.md`:** dev-vs-prod compose split, and whether the
   frontend proxies `/api` to the backend (Next rewrites) or calls the backend directly.
4. **Tests.** The SQLite suite is backend-only — the frontend needs no entry in
   `app/tests/`. If you add any Python (e.g. a serve-static or a smoke helper), keep the suite
   green (`uv run python -m app.tests`, currently 147). A smoke test for the full stack can
   live in `run_tests.py` (live server) rather than the SQLite suite.
5. **Docs.** Architecture §4.1 (project structure — add the `frontend/` tree) and §9
   (roadmap checkboxes); `plan.md`/`progress.md` for the shipped slices. Update OPEN items in
   `design-decisions.md` if any get settled.
6. **Commit & push**, then overwrite this HANDOFF with the new session summary + a fresh
   mini-plan for the *next* item (README/final polish).

## Gotchas

- Postgres runs on host port **5433** (`.env` sets `DB_PORT=5433`); Redis maps `6379`.
  Alembic head: **`f5a1b3c8e6d2`** (adds nullable `student_groups.incharge_email`). 22 tables.
- **Design decisions are tracked in `documentation/design-decisions.md`, not in this file.**
  Every new choice (or "considered and rejected") gets a DD-NNN entry in the same commit; the
  HANDOFF must copy the OPEN items verbatim so they get resolved. Keep OPEN items few.
- **New `Settings` fields must go in `.env.example` in the same commit** (real past miss —
  Redis and SMTP flags shipped without it; both fixed).
- **Tests: `uv run python -m app.tests`** (not pytest). Add any router touched by tests to the
  patch loop in `app/tests/conftest.py`. New test modules must be imported in
  `app/tests/__main__.py`. **No *external* Redis/Celery/SMTP in tests** — stub or fake anything
  that would touch the network; the live-delivery email tests use an in-process loopback SMTP
  server (`socketserver`), which is local.
- **Redis and email are inert in tests by default**: `conftest.py` sets `REDIS_ENABLED=False`
  and `EMAIL_ENABLED=False`. A test that needs either enables it and MUST restore the shared
  `app.config.settings` attributes (and any module attribute) in `finally`.
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
  is NOT exempt** — versioned routes require the same token. The auth rate limits are inert in
  tests (Redis off) but still apply via `request.client.host` when a fake client is installed
  — restore it after the test.
- **Error envelope:** every error returns `{"detail": ...}`; 422 and 500 add `request_id`.
  HTTPException keeps the default shape. Don't introduce a different envelope.
- **Variation semantics:** instance #1 is the deterministic baseline (seed `None`) unless
  `variation="best"`; gap criteria only reshape *seeded* re-rolls; keep `PLACEMENT_WEIGHT`
  strictly above any soft/variation term.
- **Exam specifics:** `EXAM_DATE_SEPARATION` only matters with `term_start`; OR-Tools models
  the rule relationally (§5.2) and the final full-checker pass is the safety net.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md` checkboxes.
