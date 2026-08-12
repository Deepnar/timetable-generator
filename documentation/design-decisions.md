# Design Decisions — Timetable Generator

A living log of the product/architecture decisions this project has made, and the ones still
open. Prior to this file, decisions lived only inside handoffs that are overwritten every
session — the git history preserved them, but nothing pointed a future session at them.

**Rule:** every session must (a) add new decisions here, (b) mark OPEN decisions resolved
(and how) when they are, and (c) enumerate the open ones in `documentation/HANDOFF.md` so the
next session is pointed at them. See `AGENTS.md` → "Design decisions".

**Status meanings**
- **Decided / Tested** — the decision is locked and the *suite* exercises it (unit /
  integration with fakes/mocks).
- **Decided / Wire-verified** — also proven against a real in-process transport (e.g. actual
  `smtplib` over loopback), not just a mock.
- **Decided / Live-verification pending** — logic is tested, but a real external dependency
  (a real SMTP server, real Redis, real Postgres) has not been exercised.
- **OPEN** — unresolved; must be addressed by a future session.

---

## Email Notifications on Publish (2026-08-10)

### DD-001 — HOD/admins have no table; summary recipients come from `CollegeSettings.config_json["notification_emails"]`
- **Status:** Decided / Tested. **Follow-up (open):** a real HOD role/table belongs to RBAC,
  which does not exist yet (§9 "RBAC"). When RBAC lands, re-point the summary at the HOD
  entities instead of the free-form list.
- **Context:** the publish mailer must notify HODs, but the schema has no `departments` or
  `hod` table — departments are bare strings on `faculty`/`student_groups`.
- **Decision:** store the HOD/admin summary addresses in the college singleton's free-form
  `config_json["notification_emails"]` (list of strings), surfaced through `PUT /settings/`.
- **Rejected alternatives:** a new `departments`/`hod` table (premature — there is no RBAC and
  no department entity anywhere); hardcoding a column on `college_settings` (the flag vs list
  distinction is exactly what `config_json` exists for).

### DD-002 — Class-incharge contact is a nullable `student_groups.incharge_email` column
- **Status:** Decided / Tested.
- **Context:** the mailer's third audience is the class incharge, who has no contact anywhere.
- **Decision:** add `student_groups.incharge_email VARCHAR(100) NULL` (migration
  `f5a1b3c8e6d2`). Nullable so existing rows and CSV imports are untouched; set via
  `POST /groups`.
- **Rejected alternatives:** a separate incharge model/table (overkill for one address per
  group); putting it in `config_json` (per-group data does not belong in a singleton).

### DD-003 — Publish email delivery is stdlib `smtplib`, sent from a daemon thread, and can never fail the publish
- **Status:** Decided / Wire-verified (2026-08-10: real `smtplib` dialog over an in-process
  loopback SMTP server, plus a real background-thread run). **Follow-up (open):** no retry
  queue (a failed send is logged and dropped), no per-recipient opt-out, no `/notifications`
  admin endpoint, no WebSocket/SSE push.
- **Context:** SMTP latency or an outage must not roll back or 500 a successful publish.
- **Decision:** `app/router/instances.py::publish_instance` calls
  `mail_service.dispatch_publish_notifications(id)` after the commit; the service spawns a
  daemon thread, opens its own DB session, and sends best-effort. `send_publish_notifications`
  swallows per-recipient failures and continues; the router additionally guards the dispatch
  call in try/except. STARTTLS on port 587, optional AUTH login.
- **Rejected alternatives:** Celery task (needs Redis/worker, which are opt-in); inline send
  in the request (would block publish); sending inside the DB transaction (a mail error could
  poison the commit).

### DD-004 — Mail is gated by `.env` flags, not by a `CollegeSettings` column
- **Status:** Decided / Tested. **Follow-up (open):** if a college ever needs to disable mail
  at runtime (no ops access), promote to a `mail_enabled` flag on `CollegeSettings` — the
  handoff suggested this and it was consciously skipped to avoid a migration in this session.
- **Context:** previous session's mini-plan said "consider a `mail_enabled` flag on
  `CollegeSettings` too."
- **Decision:** keep it env-driven: `EMAIL_ENABLED` + `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/
  `SMTP_PASSWORD`/`SMTP_FROM`. `is_email_enabled()` requires `EMAIL_ENABLED && SMTP_HOST &&
  SMTP_FROM`, so an unset `.env` is the default off state. Mirrors `REDIS_ENABLED`.

---

## Redis Integration (2026-08-09, recovered from handoff `3774b74`)

### DD-005 — Redis feature flags key independently, NOT off `ASYNC_GENERATION`
- **Status:** Decided / Tested.
- **Context:** the prior handoff suggested keying caching/rate-limiting/locking off
  `ASYNC_GENERATION=false`.
- **Decision:** give Redis its own `REDIS_ENABLED` (and `REDIS_URL`). Rate limiting and caching
  are useful regardless of async generation, so they get their own flag. **This is the exact
  pattern the email mailer (`DD-004`) copied.**

### DD-006 — Generation-conflict lock is resource-keyed, not run-keyed; a busy lock FAILs, it never queues
- **Status:** Decided / Tested.
- **Context:** two concurrent runs over the same resources could each compute their own empty
  published-reservation set and double-book.
- **Decision:** lock key = union of the resolved profile/combination's room/faculty/group/
  subject ids. The second run is marked `FAILED` (409 sync / FAILED row async). Disjoint
  resource sets still run concurrently.

### DD-007 — Redis-down means "feature off", never a 500 and never locking users out
- **Status:** Decided / Tested.
- **Context:** a broker outage must not break the request path.
- **Decision:** every client call degrades to a documented no-op; the rate limiter returns
  "allowed" when Redis is unreachable.

---

## Cross-timetable safety & solver posture (recovered from earlier sessions)

### DD-008 — Published reservations are per-resource sets, not a combined 5-tuple
- **Status:** Decided / Tested.
- **Context:** the original `(faculty, room, group, day, slot)` tuple only blocked an identical
  five-way match, missing real conflicts (same teacher, different room).
- **Decision:** `Scheduler._load_published_conflicts()` builds split sets
  `{"faculty"|"room"|"group": {(id, day, slot)}}`; the checker refuses any reuse of any
  dimension.

### DD-009 — The auth gate protects everything except `/health` and `/auth/*`
- **Status:** Decided / Tested.
- **Context:** "mutations only" left every read public; a new route could silently ship
  unauthenticated.
- **Decision:** one global `require_auth` middleware in `app/main.py` rejects every request
  without a valid admin JWT, exempting only `/health` and `/auth/*`. Reads are not public.

### DD-010 — Exams are a `session_type: EXAM` profile mode, not a separate table
- **Status:** Decided / Tested.
- **Context:** exam scheduling needed date separation and coexistence with running classes.
- **Decision:** reuse the weekly-template engine; a profile whose `session_type` parameter is
  `"EXAM"` turns each assignment into one EXAM session; `EXAM_DATE_SEPARATION` spaces them by
  `min_days`; the published-conflict loader exempts the examing groups' own class slots.

### DD-011 — `CUSTOM` escape hatches on closed enums instead of more migrations
- **Status:** Decided / Tested.
- **Context:** closed vocabularies blocked non-college use (exam halls, event spaces, shift
  rosters).
- **Decision:** `CUSTOM` added to `RoomType`, `SessionType`, `GroupType`, `TimetableType`;
  free-form attributes hang off `equipment_json`/`requirements_json`. Enum extension is the
  `ALTER TYPE ... ADD VALUE` pattern (never drop/recreate — see `d7a3c5e9f1b2`).

### DD-012 — `Subject.requirements_json` is the source of truth for room matching
- **Status:** Decided / Tested.
- **Context:** legacy `requires_lab` couldn't express room type + capacity + feature + session
  type needs.
- **Decision:** `requirements_json` (room_types / min_capacity / features / session_type)
  replaces `requires_lab`, which is now shorthand for `{"room_types": ["LAB"]}`. A subject
  whose requirements match no profile room schedules zero sessions (greedy warns, never uses a
  wrong room).

### DD-013 — Greedy stays the default preview solver; OR-Tools is opt-in
- **Status:** Decided / Tested.
- **Context:** CP-SAT is stronger but heavier.
- **Decision:** `algorithm="GREEDY"` default, `"OR_TOOLS"` selectable; both share
  `ConstraintChecker` domain pruning; OR-Tools adds relational rules and a weighted soft
  objective (`PLACEMENT_WEIGHT` kept strictly dominant).

---

## API Polish (2026-08-10)

### DD-014 — JSON errors use the FastAPI-default `{"detail": ...}` envelope; `request_id` joins server-side errors
- **Status:** Decided / Tested.
- **Context:** error responses were inconsistent — the 500 path returned
  `{"detail", "request_id"}`, validation returned bare `{"detail": [...]}` with no
  request context, and `PATCH /instances/{id}/slots/{slot_id}` returned a nested
  dict under `detail`.
- **Decision:** every error returns the framework-default `{"detail": ...}`
  envelope. Two global handlers in `app/main.py` lock it and add `request_id` to
  the server-side cases: `RequestValidationError` → 422 with
  `{"detail": errors, "request_id"}`, and a generic `Exception` handler → 500
  with `{"detail": "Internal server error", "request_id"}`. HTTPException responses
  keep the default shape. The observability middleware stores the id on
  `request.state.request_id` so handlers can report it; the middleware remains the
  safety net for anything raised outside the routing layer.
- **Rejected alternatives:** a richer `{"error": {...}}` envelope — it diverges
  from what every existing client and FastAPI's default handlers already emit for
  no gain.

### DD-015 — API versioning is one `/api/v1` aggregator router; unversioned routes stay live
- **Status:** Decided / Tested.
- **Context:** the roadmap called for `/api/v1/`; there was no versioned path.
- **Decision:** a single `APIRouter(prefix="/api/v1")` in `app/main.py` includes
  every router except `auth`. Unversioned routes remain mounted for backward
  compatibility (existing clients and `/docs` keep working), both paths sit behind
  the global auth gate, and `/health` + `/auth/*` deliberately stay at the root
  (the only auth-exempt paths).
- **Rejected alternatives:** changing each router's `prefix` (touches every file
  and makes the migration one-way); a `v2` path param (intrusive, needless
  churn); dropping the unversioned routes (breaks existing clients).

### DD-016 — Every top-level list endpoint paginates; sub-resource lists stay unbounded
- **Status:** Decided / Tested.
- **Context:** only `rooms`/`faculty`/`groups`/`subjects`/`assignments`/`audit`
  paginated; `profiles`, `constraints/hard`, `constraints/soft`, `history`,
  `blackouts`, and `faculty_availability` returned every row.
- **Decision:** all top-level list GETs paginate through the shared
  `app/utils/pagination.py` (`?skip=`/`?limit=`, `X-Total-Count`). `GET /profiles/`
  folds the page window into its Redis cache key and restores the total header on
  cache hits. Sub-resource lists (`/instances/{id}/slots`,
  `/profiles/{id}/resources`, `/profiles/{id}/parameters`,
  `/profiles/combinations`) stay unpaginated — they are bounded by one parent row.
- **Rejected alternatives:** paginating the sub-resource lists — unnecessary for
  collections that cannot grow past a single parent's data.

---

## Frontend & full-stack Dockerization (2026-08-10)

### DD-017 — Frontend is a Next.js 14 App Router + TypeScript + Tailwind app in `frontend/`
- **Status:** Decided / Tested (built, live-verified against the running API in the dockerized stack).
- **Context:** the roadmap's Phase 4 (plan.md) calls for a full frontend for college admins.
- **Decision:** `frontend/` is a hand-rolled Next.js 14 App Router app (TypeScript, Tailwind, `npm`),
  client-side pages that fetch the versioned `/api/v1` endpoints directly. First slice = Auth
  (login + JWT in localStorage), Dashboard (resource counts + recent generation runs + quick
  actions), and Resource tables (rooms/faculty/groups/subjects with server pagination, filters,
  create/edit/delete modals). Shared `ResourceTable` config drives the four CRUD pages.
- **Rejected alternatives:** `create-next-app` scaffolding (interactive, noisier for a monorepo);
  SSR-heavy data fetching (every route is behind JWT auth, so client-side keeps the token handling
  in one place); a SPA framework like Vite+React (App Router gives the routing/middleware for free).

### DD-018 — One top-level `docker-compose.yml` runs the whole stack; `docker/docker-compose.yml` stays backend-only dev infra
- **Status:** Decided / Live-verification pending (both images build; the app service was
  live-verified against Postgres+Redis; the full four-service bring-up was blocked only by a host
  port conflict on :3000, not by the compose file).
- **Context:** the roadmap wanted a one-command full-stack bring-up; only `docker/docker-compose.yml`
  (Postgres + Redis) existed.
- **Decision:** a top-level `docker-compose.yml` builds the backend (`Dockerfile`, uv official image,
  entrypoint runs `alembic upgrade head` then uvicorn) and the frontend (`frontend/Dockerfile`,
  multi-stage Next standalone) and runs App + Frontend + PostgreSQL + Redis with healthchecks.
  `docker/docker-compose.yml` remains the lighter backend-only dev infra. No separate dev/prod
  compose split yet — the top-level compose is both the demo and the deployment artifact; a prod
  split (TLS, non-root images, nginx) is deferred to the README/deploy session.
- **Rejected alternatives:** extending `docker/docker-compose.yml` into the full stack (that file is
  meant to be the lightweight dev infra and is used by backend devs who run uvicorn on the host); a
  separate `docker-compose.dev.yml` / `docker-compose.prod.yml` (no need yet — one file covers it).

### DD-019 — The frontend calls the backend directly via `NEXT_PUBLIC_API_URL`, no Next rewrite proxy
- **Status:** Decided / Live-verified (browser-facing login → versioned list/create ran against the
  dockerized backend; CORS allow-list already covers `http://localhost:3000`).
- **Context:** the frontend must reach the API; the API is already CORS-enabled for
  `http://localhost:3000` and versioned under `/api/v1`.
- **Decision:** the API client (`frontend/src/lib/api.ts`) builds full URLs from
  `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`) and talks to `/api/v1/*` directly (plus
  the root `/auth/login`). The Next image bakes the URL at build time via a build arg. No `next.config`
  rewrites/proxy layer. Auth stays simple: the browser holds the JWT and sends it as a Bearer header.
- **Rejected alternatives:** Next rewrites proxying `/api/*` → backend — adds a server-side hop,
  complicates the versioned + root-auth path mix, and is unnecessary when CORS already permits the
  frontend origin.

---

## Scale testing the generation engine (2026-08-10)

### DD-020 — A seeded full-college dataset + battle-test runner verify the engine at realistic scale
- **Status:** Decided / Live-verified (real Postgres + real Redis + the real Celery worker).
- **Context:** all 152 prior tests used tiny fixtures (1-2 divisions, a handful of sessions) that
  prove *correctness* but never the *engine at realistic size*. A real TCET-style college needed to
  be exercised to know whether greedy/OR-Tools scale and whether exports hold up.
- **Decision:** `scripts/seed_demo.py` seeds a 12-department college modeled on the `sample/` TCET
  timetables and syllabus PDFs: 576 subjects (8 sems x 6), 345 faculty (~40 in COMP, real TCET
  names), 192 groups (2 divisions/sem), 204 rooms, 1152 subject-assignments, and 108 profiles
  (DIVISION-scoped per dept/sem + DEPARTMENT-scoped per dept), wired to the real TCET time grid
  (8 x 1h slots, 08:30 start, lunch after slot 4, Mon-Sat). `scripts/battle_test.py` runs real
  generations through the same `Scheduler` the API uses; `scripts/api_drive.py` / `scripts/async_drive.py`
  drive the live HTTP API including the real Celery worker + Redis async path.
- **Findings:**
  - Greedy places all 288 sessions of a whole-department profile in ~4-4.5s across all 12
    departments; per-semester profiles place all 36 in <0.2s; 3 instances x 288 in ~12.3s.
  - OR-Tools places all 36 sessions of a per-semester profile (5s CP-SAT timeout dominates);
    whole-department OR-Tools is intentionally not exercised (the CP-SAT variable explosion is
    not the intended use — greedy is the whole-dept preview solver).
  - **Two real bugs surfaced and fixed:** unfiltered multi-group PDF export crashed with
    ReportLab `LayoutError` (now one grid per group); `GenerationResponse` omitted
    `run_duration_ms`. Tests added (154 total).
  - Cross-timetable safety confirmed live: after publishing a department's instance, a re-run over
    the same resources places fewer sessions (published reservations block reuse, per DD-008).
  - The generation lock confirmed live: concurrent overlapping runs → one COMPLETED, one LOCKED.
- **Rejected alternatives:** faking scale in the unit suite (the suite must stay fast and SQLite;
  scale testing belongs in `scripts/`, not `app/tests/`); using the tiny CSV fixtures (they are 3-4
  rows and cannot stress anything).

---

## RBAC (2026-08-11)

### DD-021 — Role-based access control on the `Admin` model with role claims in the JWT
- **Status:** Decided / Tested (four RBAC tests, 173 total).
- **Context:** the product is single-role today — every `Admin` can do everything, and there is no
  way to give a college HODs/teachers/students scoped logins. The user explicitly wants RBAC before
  deployment.
- **Decision:** add a `role` column to `admins` (migration `48c4fc85dd73`), values `admin` /
  `hod` / `teacher` / `student`, defaulting to `admin` so existing rows and the public
  self-registration path keep working. The JWT carries the role claim; `require_roles(...)` is a
  dependency that 403s when the token's role isn't allowed (no DB hit). `GET /auth/me` exposes the
  caller's identity + role for the frontend shell. Admin-only `POST /auth/users` provisions
  non-admin roles. The global auth gate still requires a valid token; `require_roles` adds the
  finer per-endpoint gates.
- **Follow-up (open):** teacher/student **read-scoping** — a teacher should only see their own
  schedule and a student only their group's published timetable. That means filtering every list
  endpoint by the caller's identity, which is a larger surface best done with the frontend (which
  will drive which views each role sees). The role infrastructure + `/auth/me` are the foundation.
- **Rejected alternatives:** separate `hod`/`teacher`/`student` tables (overkill — the Admin table
  already carries identity + auth; roles are a column, not entities); cookie sessions (JWT is the
  existing mechanism and already rides the global middleware).

---

## Teacher-workload product direction (2026-08-11)

### DD-022 — The product is positioned "for teachers"; the roadmap is a live date-aware layer + a change loop
- **Status:** Decided (strategy brief from a `deepseek-v4-pro` strategist subagent; not yet built).
- **Context:** the founder wants the product framed around cutting a teacher's daily workload, and
  specifically wants: teacher-only schedule view + own-slot exports; a "live" timetable
  (yearly/monthly/daily views, one-day shifts, "where is teacher X"); and other workload cutters.
- **Decision:** validated + refined by the strategist into this priority order:
  1. **Teacher self-service schedule + own-slot exports** — *S.* The exports already accept
     `faculty_id` (PDF/CSV/iCal); add a teacher-facing "my published schedule" read endpoint +
     the `/my-schedule` frontend page. Sells the teacher persona, removes the #1 admin chore.
  2. **Live date-aware timetable + day card** — *M.* Add a date-resolution layer: a
     `timetable_overrides` exception table (date-scoped slot moves/covers/shifts) so "is there
     class on date X / today" works. This is the platform every date-specific feature (shifts,
     covers, room changes, alerts, "where is teacher X") builds on. `GET /my/today` powers a
     day-card UI.
  3. **Change loop: room change + cover + notifications** — *M.* Room change = PATCH (exists) +
     notify; cover = a date-scoped teacher swap on the overlay + `cover_log` + notify; a small
     `app_notifications` table + hooks on publish/override/cover. Reuses the existing SMTP path
     (DD-003/DD-004 open items become relevant here).
  - Deferred: one-day shifts (rides the overlay but costs most), room-swap, push alerts.
- **Rejected alternatives:** a separate "live shift" entity + scheduler support up front (too
  early; the overlay table first is cheaper and unblocks everything); real push (FCM) before a
  mobile client exists (defer); "where is teacher X" as a standalone feature (fold into #2).

---

## Editing & comparison surfaces (2026-08-11)

### DD-023 — Instance comparison is computed client-side; the only new backend is a slot-revalidate dry-run endpoint
- **Status:** Decided / Tested (revalidate endpoint covered by the suite: 179/179; compare page verified live against seeded instances).
- **Context:** the Phase 4 editing/comparison work needed (a) side-by-side instance diffing and (b) a slot-override UI whose Save button is gated behind a clean constraint check. The handoff suggested a compare endpoint "only if the diff can't be computed client-side from the two slot lists" — it can, so none was added.
- **Decision:**
  - **Compare is frontend-only.** `/instances/compare?a=&b=` fetches both instances' `/slots` lists and diffs them client-side: per-cell add/remove/change markers (reusing the TimetableGrid's color map), a summary bar (score/violation/moved deltas), and a click-to-scroll diff list. Two grids scroll-sync via shared container refs. The two candidate instances are themselves the "plan" — no backend state changes.
  - **Slot override revalidation is a new endpoint.** `POST /instances/{id}/slots/{slotId}/revalidate` accepts a `SlotOverrideDraft` (the mutable fields of `SlotOverride` without the required reason) and returns `{"slot_id", "violations": [...]}` with **200 even on conflicts**, so the frontend can show "no conflicts" (green) or the violation list (danger) without persisting. The PATCH keeps 409-on-conflict semantics; both share the extracted `_check_candidate` helper. When a move only changes `slot_number`, the backend re-derives `start_time`/`end_time` from the profile's time grid (`_slot_time_grid`, mirroring the greedy solver) so the stored row stays consistent with `day_start_time`/`slots_per_day` without the client knowing those params.
- **Rejected alternatives:** a backend compare/diff endpoint — the two `/slots` lists are already loadable and the diff is a pure function of them; a server-side diff adds an endpoint for logic that runs fine in the browser. Making the PATCH the only revalidation path — it 409s and would need the UI to parse the error body; a dedicated dry-run keeps the edit flow non-destructive.
- **Follow-up (open):** slot override currently operates on the first slot of a merged lab block (a block is stored as per-slot rows); editing a whole block at once is a possible polish. Compare lacks a server-side "sessions by identity moved" computation — the client heuristic treats same-identity-at-different-position as moved, which is good enough for the admin surface but is worth re-checking when teacher/student portals (DD-022) land.

---

## Domain model reality-check (2026-08-11)

### DD-024 — The college's real scheduling rules need a batch layer, session-type subject ties, and per-day time grids
- **Status:** OPEN — flagged by the founder; **nothing built yet**, these are the "things to check and work on" for the next engine/domain sessions.
- **Context:** the founder described how timetables actually work at the college, and several of these rules are only partially represented (or missing) in the current schema/engine:
  1. **Batches, not just divisions.** A class is split into batches — **2 batches for 2nd–4th year, 3 batches in 1st year**. Practicals run one batch against one subject while another batch runs a different subject at the same time (2-hour parallel sessions). `student_groups.group_type` already has a `BATCH` enum value, but the seed only creates DIVISION groups and the solver schedules against the division, not batches.
  2. **One practical subject per day, max.** Per group/batch, at most one practical (LAB) subject per calendar day. `SAME_SUBJECT_SAME_DAY` already caps one block of the same subject per day, but nothing prevents two *different* lab subjects on the same day.
  3. **Subjects are tied to TUTORIAL and/or PRACTICAL.** A subject declares whether it has a tutorial, a practical, or both — each a distinct session stream. `SessionType.TUTORIAL` and `SessionType.LAB` exist as enum values, and `Subject.requirements_json` carries a `session_type`, but there is no per-subject "has tutorial / has practical / both" attribute driving two session streams.
  4. **Time grid can differ per day.** College timings may vary day-to-day (per-department or per-year consistency), with different break times and per-lecture durations. The engine currently builds **one** slot grid (`_build_slot_times` in the greedy solver) shared across every working day — there is no per-day `{day: slots[]}` structure.
  5. **Conflicts must be checked against ALL active timetables.** The cross-timetable reservation loader (`Scheduler._load_published_conflicts`) only reserves `PUBLISHED` slots. The founder wants the checker to refuse reuse against every *active* timetable (i.e. also DRAFT/SELECTED candidates, not just the published one).
- **Rejected alternatives:** none yet — this is scoped as a verification + design exercise, not an implementation.
- **Next steps (check each against the real data, then design):**
  - Add batches as `StudentGroup(group_type=BATCH, parent_division?)` and decide whether a practical slot is scheduled per batch or per division (parallel 2h sessions imply per-batch slots, one lab subject per day).
  - Extend the subject model with explicit tutorial/practical flags (or a small `subject_sessions` mapping) and let `subject_assignments` target batch/stream explicitly.
  - Refactor the time-grid builder to `{day_of_week: [(start, end), ...]}` so each day can carry its own slots/breaks/durations; profile params become per-day.
  - Change the conflict loader to take the set of "active" instance statuses (DRAFT/SELECTED/PUBLISHED) and add a college flag or profile param to choose the strictness.

---

## Single-college posture & data ownership (2026-08-11)

### DD-025 — Build for one college at a time; everything college-specific is data, and class/batch structure is teacher-set with system suggestions
- **Status:** Decided (product posture; no code yet — shapes DD-024 and every future engine change).
- **Context:** the founder wants the product to serve a single college first and generalize later, only if a second college actually appears. They also keep remembering small real-world details (class strengths, batch splits, timings), and it is unclear who decides how a class is divided into batches — the teacher or the system.
- **Decision:**
  1. **Single-tenant by default; generalize only on demand.** Ship for one college. Every college-specific fact — departments, class strengths, batch counts, working days, per-day timings, break times, lecture durations, session patterns — is **data**, never hardcoded engine logic: `college_settings` rows (the id=1 singleton already embodies this), `student_groups`, `profile_parameters`. When a second college appears the move is additive (a real `colleges` table + `college_id` FKs + scoped queries), not a rewrite, precisely because nothing college-specific is baked into the solver/checker. Until then, no `college_id` columns and no multi-college plumbing.
  2. **Class strength and batch division are teacher-set, system-suggested.** The college enters the real strength per group; the system *suggests* a split (e.g. `ceil(strength / min_capacity)` for a lab subject, or the batch counts from DD-024) but the teacher confirms or edits it, and the decision is **stored as data**, never recomputed silently. Batches are real `StudentGroup(group_type=BATCH)` rows the teacher maintains; the solver schedules against them but never invents them. This is the same "suggest, allow override" pattern as the assignment grid's Auto-fill.
  3. **A capture log for remembered details.** Because the founder surfaces small facts incrementally, each new detail is logged in the section below with two tags — *system rule vs college data* and *teacher-set vs system-set* — and only promoted to code when it is stable and genuinely cross-college.
- **Rejected alternatives:** a full multi-tenant schema now (YAGNI — no second college exists, and premature `college_id` FKs make every query heavier for zero benefit); the system auto-deciding batch splits (the college knows real enrollment and constraints the system cannot see — which students stay together, per-division lab capacity, who teaches which batch).

### Founder detail log (capture — things remembered as we go)

Rules: every detail gets two tags — **source** (`system rule` = solver/checker behavior, `college data` = rows an admin sets) and **ownership** (`teacher-set` = teacher/college enters it, `system-set` = engine computes it). Details are promoted to real design work via DD-024/DD-025; this log is the inbox, not the plan.

| # | Detail (as remembered) | Source | Ownership | Home |
|---|---|---|---|---|
| 1 | Class split into batches: 2 for 2nd–4th yr, 3 in 1st yr | college data | teacher-set | DD-024 |
| 2 | Parallel 2h practicals: one batch on subject A, another on subject B at the same time | system rule (solver) | — | DD-024 |
| 3 | Max one practical subject per day | system rule (checker) | — | DD-024 |
| 4 | Subjects tied to tutorial / practical / both | college data | teacher-set | DD-024 |
| 5 | Timings can differ per day; consistent per department/year; breaks + lecture length vary | college data | teacher-set | DD-024 |
| 6 | Number of students in the class (strength) | college data | teacher-set | DD-025 |
| 7 | How batches are divided | college data | teacher-set (system suggests from strength/capacity) | DD-025 |
| 8 | Conflicts must be checked against **all active** timetables, not just published | system rule | — | DD-024 |
| 9 | Locked/running timetable: pick boxes (cells) and change them manually mid-year | system rule (UI) | teacher-set | DD-026 |
| 10 | When changing a slot, list teachers available for the specified year to pick from | system rule (query) | teacher-set | DD-026 |
| 11 | Option for a temporary timetable for some period (date-scoped) | system rule (UI) | teacher-set | DD-026 |
| 12 | Option to swap two lectures | system rule (UI) | teacher-set | DD-026 |
| 13 | A visible change list; changes saved and shown, revertible | system rule (UI) | — | DD-026 |

---

## Mid-year change loop (2026-08-12)

### DD-026 — In-term changes to a published timetable are a `timetable_overrides` exception layer, not slot mutation
- **Status:** Decided / Tested (7 change-loop tests, 186 total). Schema: new `timetable_overrides` table (migration `d319882e1438`), 23 tables total.
- **Context:** the founder described the in-term change workflow: a teacher leaves mid-year, a room becomes unavailable, two lectures must swap, or a class runs on a temporary window. Published timetables are normally immutable (re-generate + re-publish is the workflow), but that is too heavy for a single manual correction, and editing the published slots directly would silently lose the base plan.
- **Decision:** record each change as a `TimetableOverride` row against the published instance — the base slots stay authoritative and the change set is auditable and reversible:
  - `override_type`: `TEACHER_COVER` / `ROOM_CHANGE` / `SWAP` / `TEMP` / `CUSTOM`.
  - `slot_id` = the slot being changed (old values are read from it at apply time); `new_faculty_id` / `new_room_id` hold what the change swaps in; `swap_with_slot_id` pairs the two slots of a SWAP.
  - `date_from` / `date_to` are NULL for a permanent change and set for a **temporary window** (`TEMP`); `resolved_at` marks a reverted/ended change (the row is kept as history).
  - New endpoints under `/instances/{id}`: `GET /overrides` (change list with old/new names resolved for display), `POST /overrides` (create, **conflict-checked**), `POST /slots/{id}/swap` (swap convenience wrapper), `DELETE /overrides/{oid}` (resolve/revert), `GET /overrides/available-faculty` (candidate teachers free at a day/slot, excluding instance bookings + active overrides + published reservations).
  - **Validation posture:** a change is checked against the instance's *other* slots, the other active overrides, and the cross-timetable published reservations — the data-driven profile constraints are deliberately skipped for a mid-year edit, because the change must not break the *published* plan and the profile may have changed since publication. A conflict is a 409 and nothing is saved.
- **Rejected alternatives:** editing `timetable_slots` in place (loses the base plan, no audit trail, a bad edit is unrecoverable); a new instance + re-publish per change (too heavy for one correction and would re-run the solver); hard-deleting a change (the resolve flag keeps history).
- **Follow-up (open):** the frontend "change mode" on the published instance viewer (cell selection, candidate picker, change list, revert) is the UI half of this — see the HANDOFF next-task list. The `GET /my/today` date-resolution layer (DD-022 #2) will read `timetable_overrides` to answer "is there class on date X"; the `available-faculty` endpoint already feeds that cover picker.

---

## OPEN decisions for the next session

Address these in the next session; resolved ones move up into the log with their outcome.

1. **DD-004 follow-up** — promote mail gating to a `CollegeSettings.mail_enabled` flag, or
   keep env-only? (Likely keep env-only until a college asks; but decide and record.)
2. **DD-003 follow-up** — do publish notifications need a retry queue / per-recipient opt-out /
   an admin `/notifications` endpoint? (Currently: log-and-drop.)
3. **DD-001 follow-up** — RBAC now exists (DD-021): the publish mailer can be re-pointed from
   `config_json["notification_emails"]` to real HOD-role accounts. Worth doing when the
   notifications endpoint lands.
4. **DD-018 follow-up** — the four-service compose bring-up could not bind host port 3000 on the
   dev machine (occupied by another container); the frontend image itself was verified on an
   alternate port. Next session: run the full `docker compose up` on a free 3000 and confirm
   login → dashboard in a browser, then mark DD-018 Live-verified.
5. **DD-020 follow-up** — the seeded dataset lives in the local Postgres; decide whether the seed
   script + battle-test runner should be wired into CI or kept as local dev tooling. Also decide a
   cadence for re-running the battle test (e.g. after any engine/solver change).
6. **DD-021 follow-up** — teacher/student read-scoping (see the DD-021 entry): filter list
   endpoints by the caller's identity once the frontend defines which views each role needs.
7. **DD-022 follow-up** — build order for the teacher-workload roadmap: (1) teacher self-service
   schedule + own-slot exports, (2) the `timetable_overrides` date-resolution layer + day card,
   (3) the change loop (room change + cover + notifications). The strategist brief recommends
   exactly this sequence; the assignment grid has shipped and the teacher portal is next.
8. **DD-023 follow-up** — block-level overrides: the slot editor edits a single per-slot row, so
   moving one slot of a merged lab block leaves its siblings behind. Consider operating on the
   whole block. Also re-check the client-side "moved session" heuristic when the teacher portal
   lands.
9. **DD-024 (OPEN)** — the college's real rules: batches (2 batches 2nd–4th yr, 3 in 1st yr, with
   parallel 2h practicals), max one practical subject per day, per-subject tutorial/practical
   ties, per-day time grids (varied timings/breaks/lecture duration), and conflict checking
   against ALL active timetables (not just PUBLISHED). Verify each against the real data, then
   design — see the DD-024 entry for next steps. **Implement under the DD-025 posture**: the
   college data is teacher-set (system only suggests), and every detail goes through the founder
   detail log before it becomes code.
10. **DD-025 follow-up** — keep the single-college posture honest: as new features land, resist
    hardcoding college-specific behavior; anything the college can differ on should be a data
    row (settings / group / parameter), not engine logic. Revisit multi-tenant only when a second
    college asks. The founder detail log is the inbox for remembered details — keep it pruned as
    items get resolved into DD entries.
11. **DD-026 follow-up** — the mid-year change layer is fully shipped (schema + conflict-checked
     endpoints + change-mode UI with candidate-teacher picker and a revertible change list). Next:
     the `GET /my/today` date-resolution layer (DD-022 #2) should resolve overrides by date (a
     TEMP window hides a covered slot outside its dates, a permanent cover wins inside it), and a
     college flag could gate whether changes are allowed on locked timetables at all.

---

## Past misses (found in audit — tracked so they do not repeat)

- **`.env.example` drift** — the Redis session added `REDIS_URL`/`REDIS_ENABLED` but never
  added them to `.env.example`; the email session added `SMTP_*` the same way. Now fixed (both
  added). Rule: **any new `Settings` field must be added to `.env.example` in the same commit.**
- **Decisions lived only in overwritten handoffs** — this file is the fix; git history is the
  backup, not the living record.
