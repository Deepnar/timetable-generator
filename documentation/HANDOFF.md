# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, and commit rules. Then read
the sections below. This file is overwritten at the end of every session; the git history
preserves older handoffs.

**Design decisions live in `documentation/design-decisions.md`** (a permanent ADR log — not
here). The OPEN items below are copied from it; resolve them and mark them done in the log.

**A new opencode agent exists**: `.opencode/agents/strategist.md` is a read-only subagent on
`opencode-go/deepseek-v4-pro` for product framing / feature ideation / roadmap prioritization.
Spawn via the `task` tool with `subagent_type: "strategist"`. **Workflow rule from the user:**
use the cheap `opencode-go/mimo-v2.5` (the saved vision default) for routine screenshot/visual
checks; use `opencode-go/qwen3.8-max` ONLY for frontend design critique; use the strategist
(deepseek-v4-pro) ONLY for high-value product strategy. Do not over-use the big models.

---

## Session summary (committed & pushed)

State at handoff: **179/179 tests passing** (`uv run python -m app.tests`), frontend builds
(`npm run build`), tree clean, all pushed. Both dev servers running (backend :8000, frontend
:3001) — see Gotchas if not.

**Login credentials** (TCET-style seed data, 12 departments, 204 rooms / 576 subjects etc.):
`admin@example.com` / `admin123` (admin) · `teacher1@tcet.edu.in` / `teach123` (teacher) ·
`student1@tcet.edu.in` / `stud123` (student) · `hod@scale.edu.in` / `pass123` (HOD).

**This session finished the Phase-4 scheduling surfaces and built the profile/constraint
builder**, plus recorded the founder's real-college scheduling rules as an OPEN design item:

1. **Assignment grid** (commits `a53e69c`, `2170714`) — `/assignments`: subject × group matrix
   scoped by department + semester (rows = subjects, columns = division groups), faculty
   avatar + hours badge per cell, anchored cell editor over the existing `subject_assignments`
   CRUD, per-subject coverage chips, and a least-loaded-faculty **Auto-fill** bulk action.
2. **Profile & constraint builder** (commits `2a57e6e`, `1979d9d`) —
   - `/profiles`: preset card grid (scope/semester/department badges, description, archive)
     with a create drawer; creating jumps straight to the detail page.
   - `/profiles/[id]`: four tabs — **Resources** (per-type shuttles over rooms/faculty/groups/
     subjects with attached counts), **Parameters** (catalog-driven key/type/value rows with
     JSON validation, inline edit), **Constraints** (hard + soft rows from `GET /constraints/types`,
     inline soft-weight editing), **Runs** (the profile's generation history).
   - The generate page now accepts `?profile=N` so the detail page's Generate button preselects,
     and gained the `<Suspense>` wrapper `useSearchParams` needs during prerender. A `Tabs` UI
     primitive joined the component kit (radix tabs was already a dependency).
3. **DD-024 — domain reality check** (`1979d9d`) — the founder described the college's actual
   rules, several of which are only partially modeled. **Recorded as OPEN, nothing built yet:**
   batches (2 batches 2nd–4th yr, **3 in 1st yr**, with parallel 2h practicals — one batch on
   one subject while another batch runs a different subject at the same time); max **one
   practical subject per day**; per-subject **tutorial/practical/both** ties (two session
   streams); **per-day time grids** (timings/breaks/lecture duration can vary by day, consistent
   per department/year); and conflict checking against **ALL active timetables** (the loader only
   reserves PUBLISHED slots today). See the DD-024 entry for verified next steps.

**Backend reality that matters for the product**: rooms are a shared pool — the solver assigns a
room per session from the subject's `requirements_json`, so a subject is taught in different
rooms across the week (matches the user's college; no fixed classroom per subject). The engine,
RBAC, exports, async generation, constraint registry, all six soft constraints, compare,
slot-override revalidation, the assignment grid, and the profile builder are built and tested.

---

## Open design decisions (from `documentation/design-decisions.md` — resolve these)

1. **DD-004 follow-up** — promote mail gating to a `CollegeSettings.mail_enabled` flag, or keep
   env-only? (Likely keep env-only until a college asks; but decide and record.)
2. **DD-003 follow-up** — do publish notifications need a retry queue / per-recipient opt-out /
   an admin `/notifications` endpoint? (Currently: log-and-drop.)
3. **DD-001 follow-up** — RBAC now exists (DD-021): re-point the publish mailer from
   `config_json["notification_emails"]` to real HOD-role accounts. Worth doing when the
   notifications endpoint lands.
4. **DD-018 follow-up** — the four-service compose bring-up could not bind host port 3000 (an
   unrelated container owns it on this machine); the frontend image was verified on an alternate
   port. Confirm a full `docker compose up` on a free 3000 in a browser, then mark Live-verified.
5. **DD-020 follow-up** — decide whether `scripts/` (seed + battle test + full_stack_test) should
   be wired into CI or stay local dev tooling; set a cadence for re-running the battle test.
6. **DD-021 follow-up** — teacher/student read-scoping: filter list endpoints by the caller's
   identity once the frontend defines which views each role needs (the teacher portal will drive
   this).
7. **DD-022 follow-up** — build order for the teacher-workload roadmap: (1) teacher self-service
   schedule + own-slot exports, (2) the `timetable_overrides` date-resolution layer + day card,
   (3) the change loop (room change + cover + notifications). The strategist brief recommends
   exactly this sequence; the assignment grid and profile builder have shipped and the teacher
   portal is next.
8. **DD-023 follow-up** — block-level overrides: the slot editor edits a single per-slot row, so
   moving one slot of a merged lab block leaves its siblings behind. Consider operating on the
   whole block. Also re-check the client-side "moved session" heuristic when the teacher portal
   lands.
9. **DD-024 (OPEN)** — the college's real rules: batches (2 batches 2nd–4th yr, 3 in 1st yr, with
   parallel 2h practicals), max one practical subject per day, per-subject tutorial/practical
   ties, per-day time grids (varied timings/breaks/lecture duration), and conflict checking
   against ALL active timetables (not just PUBLISHED). Verify each against the real data, then
   design — see the DD-024 entry for next steps.

---

## Next task — teacher portal (DD-022 #1); then the DD-024 batch/domain layer

All of the scheduling + configuration surfaces from the design plan are now shipped. Remaining,
in the recommended order:

1. **Teacher portal** (DD-022 #1) — `/my-schedule`: teacher sees only their slots (the exports
   already accept `?faculty_id=`), exports own iCal/PDF, and a "today" card. Requires either
   server-side caller scoping on the slots read (DD-021 follow-up) or a `GET /my/schedule`
   endpoint — the design plan calls for confirming `app/router/instances.py` first. Then #2 (the
   `timetable_overrides` date-resolution layer + day card), then #3 (the change loop).
2. **DD-024 domain work** — the batch/tutorial/per-day-grid requirements the founder described.
   This is a design exercise first (see the DD-024 entry): verify each rule against the real
   college data, then decide the model (batch groups + parallel practicals, per-subject
   tutorial/practical flags, per-day time grids, all-active-timetable conflict reservations).
   It will touch `app/models/`, the greedy/OR-Tools solvers, the checker, and the seed.
3. Optional polish: CSV upload modals on resource pages; WebSocket progress for async runs;
   a `/constraints` reference catalog page (the data is already exposed via `GET /constraints/types`).

Keep the docs in sync (architecture §3/§4/§5/§8, plan.md, progress.md) and record any new
decision in `design-decisions.md`.

---

## How to run

```bash
# infra (Postgres :5433, Redis :6379) — already running on this machine
docker compose -f docker/docker-compose.yml up -d

# backend (migrations run on boot in docker; manually here)
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# seed the TCET-style dataset (12 depts / 576 subjects / 345 faculty / 204 rooms / 108 profiles)
uv run python -m scripts.seed_demo --wipe

# frontend on :3001 (port 3000 is owned by an unrelated container on this machine)
cd frontend && npm install && npm run dev -- -p 3001 &

# screenshots: node scripts/screenshot.mjs  (real login + per-page capture → /tmp/opencode/shots)
# verify visually via the vision skill (mimo for routine checks)
```

Full backend verification: `uv run python -m app.tests` (179) · scale: `scripts/full_stack_test.py`
(after a fresh seed; server must be up) · live API drive: `scripts/api_drive.py`,
`scripts/async_drive.py` (async needs ASYNC_GENERATION=true + a celery worker).

---

## Gotchas

- Postgres :5433, Redis :6379; Alembic head `48c4fc85dd73` (admins.role; prior `1d8688977519`
  added placement_warning). 22 tables.
- **`npm run build` corrupts a running `next dev` `.next` cache** — after any build, kill the dev
  server, `rm -rf frontend/.next`, restart dev. Also always restart dev after pulling/committing.
- **The backend dev server runs WITHOUT `--reload`** (uvicorn started by `nohup` in this session
  to keep it stable). After editing backend code, restart it manually — a stale server silently
  serves old routes (the revalidate endpoint 404'd until a restart last session).
- **Design decisions are tracked in `documentation/design-decisions.md`**, not in this file. Every
  new choice gets a DD-NNN entry in the same commit; the HANDOFF copies OPEN items verbatim.
- **New `Settings` fields must go in `.env.example`** in the same commit (real past miss).
- **Tests**: `uv run python -m app.tests` (not pytest). No external Redis/Celery/SMTP in tests;
  `conftest.py` forces them off. New routers touched by tests must be in the conftest patch loop.
- **The auth gate is global** — every route except `/health` and `/auth/*` needs a JWT;
  `/api/v1/*` is not exempt. Role claims ride the JWT; `require_roles()` gates finer endpoints.
- **Error envelope**: every error returns `{"detail": ...}`; 422/500 add `request_id`. The CORS
  `expose_headers` now lets the browser read `X-Total-Count`/`X-Request-ID` — keep that.
- **Frontend data fetching**: all via TanStack Query (`src/hooks/use-resources.ts`); pages are
  `"use client"`. `useSearchParams` pages need a `<Suspense>` wrapper (see `/instances/compare`
  and `/generate`).
- **Scale testing lives in `scripts/`, not `app/tests/`** (DD-020). Re-baseline after engine
  changes: `scripts/seed_demo.py --wipe` then `scripts/full_stack_test.py` (server up).
- **The strategist agent** needs a fresh opencode session to appear in the `task` tool list (it
  was added mid-session); it's already loaded in current sessions. `.opencode/agents/strategist.md`.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md`.
