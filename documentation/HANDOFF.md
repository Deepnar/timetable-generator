# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then
read the sections below. This file is overwritten at the end of every session; the git
history preserves older handoffs.

**Design decisions live in `documentation/design-decisions.md`** (a permanent ADR log — not
here). The OPEN items below are copied from it; resolve them and mark them done in the log.

## Session summary (committed & pushed)

State at handoff: **134/134 tests passing** (`uv run python -m app.tests`), tree clean.

Two things shipped this session:

**(A) Email Notifications on Publish** (the NEXT TASK from the previous handoff). An **opt-in
SMTP mailer** in `app/services/mail_service.py` that fires after `POST /instances/{id}/publish`
and degrades to a strict no-op when SMTP is unconfigured — the same graceful-degradation
posture as the Redis client:

1. **Config** (commit `cfb3320`) — `app/config.py` gained `EMAIL_ENABLED` (default `true`),
   `SMTP_HOST` (default empty), `SMTP_PORT` (587), `SMTP_USER`/`SMTP_PASSWORD` (optional login),
   `SMTP_FROM` (default empty). `is_email_enabled()` requires `EMAIL_ENABLED` **and** `SMTP_HOST`
   **and** `SMTP_FROM`, so an unset `.env` is the default "mail off" state.
2. **The mailer** (commit `cfb3320`) — on publish, three audiences, each getting one message
   with a PDF attachment reusing the export layer (`generate_timetable_pdf`, no new rendering):
   - *Faculty* — every faculty with a slot in the instance gets their **personal schedule PDF**;
   - *HOD / admins* — addresses in `CollegeSettings.config_json["notification_emails"]` get the
     **full-instance summary PDF** (the schema has no HOD table; the singleton's free-form
     `config_json` is the designated contact-list store);
   - *Class incharges* — every group with a non-null `student_groups.incharge_email` gets its
     **group's schedule PDF** (column added by migration `f5a1b3c8e6d2`, nullable).
   Delivery is stdlib `smtplib` (`STARTTLS` on 587, optional login), plain-text + HTML bodies.
3. **Wiring** (commit `570b43f`) — `publish_instance` calls `dispatch_publish_notifications(id)`
   after the commit, which spawns a daemon thread (never blocks the response) and is additionally
   guarded in the router, so a mailer error can never fail a successful publish. `send_publish_
   notifications` swallows per-recipient delivery failures and continues.
4. **Tests** (commit `81c9042`) — **7 new (125 → 132)** in `app/tests/test_email_notifications.py`
   (registered in `__main__.py`). `conftest.py` forces `EMAIL_ENABLED=false` so the suite never
   touches a network. Tests enable the mailer, patch `mail_service._deliver` (or
   `dispatch_publish_notifications`) and restore the shared `settings` object in `finally`.
   Coverage: faculty→personal PDF / HOD→summary / incharge→group PDF (recipients, subjects,
   `%PDF` attachments); no-slot recipients skipped; a raising delivery is logged not raised;
   unconfigured SMTP never spawns a thread and returns `[]`; publish triggers the dispatch; a
   raising dispatch still returns a 200 publish.
5. **Docs** (commit `77a7664`) — architecture §4.2 (publish endpoint note), §7.7 rewritten from
   "NOT implemented", new §8.9 notification config, §9 shipped/roadmap; `plan.md` Phase 5 and
   `progress.md` checkboxes.

**Commits (in order):** `a7c6789` (incharge_email model/schema/migration), `cfb3320` (config +
mailer), `570b43f` (router wiring), `81c9042` (tests), `77a7664` (docs).

**(B) Design-decision tracking + real-transport verification** (this session's follow-up):

1. **`documentation/design-decisions.md`** — new permanent ADR log (DD-001…DD-013) covering the
   email decisions *and* decisions recovered from the overwritten handoffs (Redis flags/locking/
   degradation, cross-timetable per-resource sets, global auth gate, exam-as-profile-mode,
   CUSTOM enum hatches, `requirements_json` precedence, greedy-default posture). It also lists
   **OPEN follow-ups** and a "past misses" audit (`.env.example` drift, decisions living only in
   handoffs). `AGENTS.md` gained the mandatory rule: record decisions in the same commit, carry
   OPEN items into the HANDOFF verbatim, resolve don't accumulate, `.env.example` for every new
   `Settings` field, and honest testing statuses.
2. **Live-delivery tests** — **2 new (132 → 134)**. `test_email_notifications.py` gained a
   "live delivery" suite that is NOT mock-only: (a) a real daemon-thread run of
   `dispatch_publish_notifications` against the SQLite pool (joined, asserts all three
   deliveries), and (b) the real `smtplib` dialog (EHLO/MAIL/RCPT/DATA) against an in-process
   loopback SMTP server (`socketserver`), asserting `From:`, `application/pdf` and all three
   recipients arrive over the wire. So the mailer is now **Wire-verified** — only a real
   external SMTP server (STARTTLS certs, auth, the network) remains for live verification.
3. **`.env.example`** — added the missing `REDIS_URL`/`REDIS_ENABLED` (missed in the Redis
   session) and the new `SMTP_*`/`EMAIL_ENABLED` vars.

**Commits (in order, this part):** <commits to be written at session end>.

## Open design decisions (from `documentation/design-decisions.md` — resolve these)

1. **DD-004 follow-up** — promote mail gating to a `CollegeSettings.mail_enabled` flag, or keep
   env-only? (Likely keep env-only until a college asks; but decide and record.)
2. **DD-003 follow-up** — do publish notifications need a retry queue / per-recipient opt-out /
   an admin `/notifications` endpoint? (Currently: log-and-drop.)
3. **DD-001 follow-up** — when RBAC lands, replace `config_json["notification_emails"]` with
   real HOD entities.
4. **Verification debt** — the async/Celery and Redis paths are tested with
   fakes/`task_always_eager`; a live Redis + live Postgres smoke test (`python run_tests.py`)
   has not been run recently. Decide a cadence for the live smoke test.

## Context to read before starting

- `AGENTS.md` (repo root) — environment, tests, commit rules, and the **Design decisions** rule.
- `documentation/design-decisions.md` — the permanent ADR log; read the OPEN section first.
- `app/services/mail_service.py` — the mailer: `is_email_enabled`, `dispatch_publish_notifications`
  (thread spawner), `send_publish_notifications` (synchronous, testable), `_build_messages`,
  `_deliver` (the only place that touches `smtplib`).
- `app/router/instances.py::publish_instance` — the guarded dispatch call after the commit.
- `app/services/redis_client.py` — the degradation pattern `mail_service` mirrors.
- `app/tests/test_email_notifications.py` — `_enable_email`/`_restore_email` helpers (mutate the
  shared `app.config.settings`, restore in `finally`), `_generate_one`, how the mailer is
  mocked, and the live-delivery suite (tracked-thread join + `_SmtpServer` loopback).
- Architecture doc **§7.7 (Email Notifications on Publish)** and **§8.9 (Notification config)**.

## NEXT TASK — Email Notifications is DONE. Next up: **API Polish**

The remaining roadmap items in priority order (details in `documentation/progress.md`):

1. **API Polish** — pagination completeness (only `assignments`, `audit`, `faculty`, `groups`,
   `rooms`, `subjects` list endpoints paginate today; `profiles`, `constraints`, `history`,
   `room_blackout`, `faculty_availibility` do not), global error middleware (the observability
   middleware in `app/main.py` already 500-wraps and logs; JSON error shape is inconsistent
   across routers), request logging/audit (done), API versioning (`/api/v1/` — not started).
2. **Frontend (Next.js/React) + full-stack Dockerization** — the planned UI
   (`documentation/plan.md` Phase 4 + progress.md 🟢) plus a top-level compose running
   App + Frontend + PostgreSQL + Redis.
3. **Final polish** — README/setup guide, historical data import, ML preference learning
   (Phase 2, from manual overrides).

## Remaining known items (see `documentation/progress.md`)

- **API Polish** — pagination completeness, global error middleware, request logging/audit
  (done), `/api/v1/` versioning.
- **Frontend + full-stack Dockerization** — Next.js app + top-level compose.
- **README & Docs, Historical Data Import, ML Preference Learning**.
- **Notification service extras** (beyond the shipped email path, §7.7): no `/notifications`
  admin endpoint, no per-recipient opt-out, no retry queue (a failed send is logged and dropped),
  no WebSocket/SSE push. `TimetableType.CUSTOM` is already in the code (commit `b9492be`) — the
  older handoff's note about it being missing is stale.

## MINI-PLAN for the next session (API Polish)

Follow exactly; commit per concern (engine / API / tests / docs separate).

1. **Scope it.** Audit which list endpoints still lack pagination (compare `rg -l "pagination"
   app/router` against every router exposing a list GET — known gaps above). Read
   `app/utils/pagination.py` (`Pagination` / `pagination` / `paginate`, `X-Total-Count` header)
   and the routers that already use it (`app/router/rooms.py`, `audit.py`) as the template.
   Decide the JSON error shape: a consistent `{"detail": ...}` envelope (FastAPI default) vs a
   richer `{"error": {...}}` — pick one and enforce it in a global exception handler in
   `app/main.py` (the current 500 path already returns `{"detail": "Internal server error",
   "request_id": ...}`). **Record the error-shape decision in `design-decisions.md` (DD-NNN)
   in the same commit.**
2. **Versioning.** Decide `/api/v1/` prefix strategy: either a top-level `APIRouter(prefix="/api/v1")`
   aggregator mounted in `app/main.py`, or a per-router prefix change. Prefer the aggregator so
   existing router files stay untouched and the current `/docs` routes keep working. Consider a
   `v2` path param instead of hardcoding if that's simpler to test. Keep `/health` and `/auth/*`
   where they are (exempt paths in the auth middleware). **Record the versioning decision in
   `design-decisions.md` too.**
3. **Tests.** Extend the suite: every newly-paginated list endpoint gets a `page`/`limit` +
   `X-Total-Count` assertion (there is already a pagination test in
   `app/tests/test_settings_and_assignments.py` — "list endpoints paginate and report
   X-Total-Count"); a global-error-shape test (an unhandled route returns the chosen envelope);
   a versioned-path smoke test (`GET /api/v1/...`). New test modules must be imported in
   `app/tests/__main__.py`. Run `uv run python -m app.tests` — must stay 134/134 + new.
4. **Docs.** Architecture §4 (endpoint listing — add the version prefix / error-envelope note),
   §7 (a new subsection if error middleware or versioning is non-trivial), and
   `plan.md`/`progress.md` checkboxes in the same change. Update the OPEN items in
   `design-decisions.md` if any get settled.
5. **Commit & push**, then overwrite this HANDOFF with the new session summary + a fresh
   mini-plan for the *next* item (Frontend + Dockerization).

## Gotchas

- Postgres runs on host port **5433** (`.env` sets `DB_PORT=5433`); Redis maps `6379`.
  Alembic head: **`f5a1b3c8e6d2`** (adds nullable `student_groups.incharge_email`). 22 tables.
- **Design decisions are tracked in `documentation/design-decisions.md`, not in this file.**
  Every new choice (or "considered and rejected") gets a DD-NNN entry in the same commit; the
  HANDOFF must copy the OPEN items verbatim so they get resolved. Keep OPEN items few.
- **New `Settings` fields must go in `.env.example` in the same commit** (real past miss — Redis
  and SMTP flags shipped without it; both now fixed).
- Tests: `uv run python -m app.tests` (not pytest). Add any router touched by tests to the
  patch loop in `app/tests/conftest.py`. New test modules must be imported in
  `app/tests/__main__.py` to register their suites. **No *external* Redis/Celery/SMTP in tests**
  — stub or fake anything that would touch the network; the live-delivery email tests use an
  in-process loopback SMTP server (`socketserver`), which is local, not external.
- **Redis and email are inert in tests by default**: `conftest.py` sets `REDIS_ENABLED=False` and
  `EMAIL_ENABLED=False`. A test that needs either enables it and MUST restore the shared
  `app.config.settings` attributes (and any module attribute, e.g. `redis_client._get_client`)
  in `finally`, or later tests see stale state.
- **The mailer's only network touch is `mail_service._deliver`** — every other function composes
  messages offline. Composition tests patch `_deliver` (or `dispatch_publish_notifications`);
  when a test runs the real background thread, keep the `_deliver` patch alive until the thread
  has been joined (the live-delivery suite shows the pattern).
- **The publish endpoint never fails on mail**: the router guards `dispatch_publish_notifications`
  in try/except, and the dispatch itself only starts a daemon thread. Keep it that way — a mail
  outage must never roll back or 500 a successful publish.
- **The lock is resource-keyed, not run-keyed**: two generations with disjoint resource
  sets run concurrently; overlapping sets are serialised. A busy lock marks the *second*
  run FAILED (409 sync / FAILED row async) — it does not queue.
- **Literal sub-routes under `/profiles` must be registered before `/{id}`** (Starlette
  path params match any single segment → a later `"combinations"` list route gets shadowed
  and returns 422). See the comment above `get_profile_combinations`.
- **Native Postgres enum migration gotcha:** `roomtype`/`sessiontype` (and any native enum)
  can only be extended with `ALTER TYPE ... ADD VALUE` inside `upgrade()` — never drop and
  recreate (the column references the type). `d7a3c5e9f1b2` is the pattern. `downgrade()` is
  a documented no-op because Postgres cannot remove a label.
- **Structural rules are always-on**: the 14 `STRUCTURAL_RULES` are dispatched regardless of
  profile `hard_constraints` rows; a row of a structural type is decorative. New *data-driven*
  rules must be registered with `@hard_rule` AND their enum member added to
  `HARD_CONSTRAINT_TYPES` (the `GET /constraints/types` catalog test asserts exact
  enum ↔ list parity).
- **`requirements_json` semantics:** an empty dict means "no constraints" even with
  `requires_lab=True`; a missing `features` tag is unsatisfiable unless the room carries it
  in `equipment_json` or a legacy boolean (`projector`/`ac`); a subject whose requirements
  match no profile room schedules zero sessions (greedy warns, never uses a wrong room).
- **Async mode is off by default** (`ASYNC_GENERATION=false`). Worker task tests call
  `run_generation(run_id)` directly; the async HTTP branch uses
  `celery.current_app.conf.task_always_eager = True`. The generation lock applies in both
  modes because it lives in `solve_generation`.
- **The auth gate is global**: tests that call a non-exempt route must pass
  `auth_headers(login_token(client))`. Only `/health` and `/auth/*` are exempt. The auth
  rate limits are inert in tests (Redis off) but still apply via `request.client.host`
  when a fake client is installed — restore it after the test.
- **Variation semantics:** instance #1 is the deterministic baseline (seed `None`) unless
  `variation="best"`; gap criteria only reshape *seeded* re-rolls; keep `PLACEMENT_WEIGHT`
  strictly above any soft/variation term so placements are never traded away.
- **Exam specifics:** `EXAM_DATE_SEPARATION` only matters with `term_start`; OR-Tools models
  the rule relationally (§5.2) and the final full-checker pass is the safety net for other
  committed-dependent registry rules.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md` checkboxes.
