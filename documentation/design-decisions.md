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

## OPEN decisions for the next session

Address these in the next session; resolved ones move up into the log with their outcome.

1. **DD-004 follow-up** — promote mail gating to a `CollegeSettings.mail_enabled` flag, or
   keep env-only? (Likely keep env-only until a college asks; but decide and record.)
2. **DD-003 follow-up** — do publish notifications need a retry queue / per-recipient opt-out /
   an admin `/notifications` endpoint? (Currently: log-and-drop.)
3. **DD-001 follow-up** — when RBAC lands, replace `config_json["notification_emails"]` with
   real HOD entities.
4. **Verification debt** — the async/Celery and Redis paths are tested with
   fakes/`task_always_eager`. A live Redis and a live Postgres smoke test
   (`python run_tests.py`) has not been run recently. Decide a cadence for the live smoke test.

---

## Past misses (found in audit — tracked so they do not repeat)

- **`.env.example` drift** — the Redis session added `REDIS_URL`/`REDIS_ENABLED` but never
  added them to `.env.example`; the email session added `SMTP_*` the same way. Now fixed (both
  added). Rule: **any new `Settings` field must be added to `.env.example` in the same commit.**
- **Decisions lived only in overwritten handoffs** — this file is the fix; git history is the
  backup, not the living record.
