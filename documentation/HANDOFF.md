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

**This session shipped Phase 4 (editing & comparison) of the design plan** (commits `624a1c6`,
`bb6a2ac`, `365167e`):

1. **Slot-revalidate dry-run endpoint** (`624a1c6`) — `POST /api/v1/instances/{id}/slots/{slotId}/revalidate`
   accepts a `SlotOverrideDraft` (the `SlotOverride` mutable fields, no required reason) and
   returns `{"slot_id", "violations": [...]}` with **200 even on conflicts** — so the UI can
   gate Save behind a clean dry-run instead of parsing a 409. The override PATCH and this
   endpoint share the extracted `_check_candidate` helper (the old `_revalidate_slot` is gone).
   When only `slot_number` moves, start/end times are re-derived from the profile's time grid
   (`_slot_time_grid`, mirroring the greedy solver's `_build_slot_times`) so the stored row
   stays consistent without the client knowing `day_start_time`/durations. Two new tests
   (179 total).
2. **Compare mode** (`bb6a2ac`) — `/instances/compare?a=&b=` fetches both instances' `/slots`
   lists and diffs them **client-side** (no backend compare endpoint — DD-023). Two
   scroll-synced TimetableGrids with per-cell `added`/`removed`/`changed` markers (reusing the
   shared subject color map), a summary bar (score/violation/moved deltas), and a click-to-scroll
   diff list. Entry points from the instances list and the instance viewer.
3. **Slot override UI** (`bb6a2ac`) — clicking a DRAFT/SELECTED cell in `/instances/[id]` opens
   a fixed-position editor (day/slot/room/faculty selects + reason). A debounced revalidate
   shows "no conflicts" (green) or the violation list (danger); Save is disabled until clean and
   commits via the existing optimistic `useSlotOverride` mutation. PUBLISHED instances are
   read-only with a warning banner. The screenshot harness now also captures the scheduling
   pages (instances / detail / compare / exports).

**Backend reality that matters for the product**: rooms are a shared pool — the solver assigns a
room per session from the subject's `requirements_json`, so a subject is taught in different
rooms across the week (matches the user's college; no fixed classroom per subject). The engine,
RBAC, exports, async generation, constraint registry, all six soft constraints, compare, and
slot-override revalidation are built and tested.

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
7. **DD-022 follow-up** — build order for the teacher-workload roadmap (after compare/slot-override
   and the assignment grid): (1) teacher self-service schedule + own-slot exports, (2) the
   `timetable_overrides` date-resolution layer + day card, (3) the change loop (room change +
   cover + notifications).
8. **DD-023 follow-up** — block-level overrides: the slot editor edits a single per-slot row, so
   moving one slot of a merged lab block leaves its siblings behind. Consider operating on the
   whole block. Also re-check the client-side "moved session" heuristic when the teacher portal
   lands.

---

## Next task — assignment grid, then profile/constraint builder, then the teacher portal (DD-022)

Phase 4's editing & comparison is done. Remaining, in the recommended order:

1. **Assignment grid** (`/assignments`) — subjects × groups matrix with faculty per cell.
   Backend `subject_assignments` CRUD exists (`app/router/assignments.py`: list/create/update/
   delete with `subject_id`/`faculty_id`/`group_id` filters). Design-plan spec: rows = subjects
   grouped by semester, columns = groups, cell = faculty avatar + weekly-hours chip, CellPopover
   to assign/edit, coverage chips, auto-suggest bulk fill. Data types needed: `Subject` has
   `department`/`semester`, `StudentGroup` has `department`/`year`/`semester`/`strength`, and
   `SubjectAssignment` carries `subject_id`/`faculty_id`/`group_id`/`weekly_hours`.
2. **Profile & constraint builder** (`/profiles`, `/profiles/[id]`) — tabs (Resources |
   Parameters | Constraints | Runs), resource shuttles, typed param fields, constraint rows with
   soft-weight sliders, dirty bar, dry-run check. Backend endpoints all exist
   (`app/router/profiles.py`, `app/router/constraints.py`); the design-plan phase-3 spec is in
   `frontend-design-plan.md` (pages 8/9).
3. **Teacher portal** (DD-022 #1) — `/my-schedule` (teacher sees only their slots, exports own
   iCal/PDF), then the date-aware overlay + day card (#2), then the change loop (#3).

Optional polish: CSV upload modals on resource pages; WebSocket progress for async runs.

Keep the docs in sync (architecture §4.1/§4.4, plan.md, progress.md) and record any new
decision in `design-decisions.md` (e.g. the assignment-grid bulk-suggest behavior).

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
  silently serves old routes (this session's revalidate endpoint 404'd until a restart).
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
  `"use client"`. `useSearchParams` pages need a `<Suspense>` wrapper (see `/instances/compare`).
- **Scale testing lives in `scripts/`, not `app/tests/`** (DD-020). Re-baseline after engine
  changes: `scripts/seed_demo.py --wipe` then `scripts/full_stack_test.py` (server up).
- **The strategist agent** needs a fresh opencode session to appear in the `task` tool list (it
  was added mid-session); it's already loaded in current sessions. `.opencode/agents/strategist.md`.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md`.
