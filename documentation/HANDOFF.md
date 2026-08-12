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

State at handoff: **186/186 tests passing** (`uv run python -m app.tests`), frontend builds
(`npm run build`), tree clean, all pushed. Both dev servers running (backend :8000, frontend
:3001) — see Gotchas if not.

**Login credentials** (TCET-style seed data, 12 departments, 204 rooms / 576 subjects etc.):
`admin@example.com` / `admin123` (admin) · `teacher1@tcet.edu.in` / `teach123` (teacher) ·
`student1@tcet.edu.in` / `stud123` (student) · `hod@scale.edu.in` / `pass123` (HOD).

**This session shipped the mid-year change loop (DD-026) and set the single-college product
posture (DD-025):**

1. **Single-college posture (DD-025, committed `ea3978c`)** — decided and recorded, no code:
   build for ONE college; everything college-specific is a data row (settings / groups /
   parameters), never hardcoded engine logic. Class strength + batch division are **teacher-set,
   system-suggested** (the system suggests a split from strength/capacity, the teacher confirms,
   stored as data — never silently recomputed). A **founder detail log** in `design-decisions.md`
   is the inbox for remembered real-world details, each tagged *system rule vs college data* +
   *teacher-set vs system-set*. Generalize to multi-tenant only when a second college asks.
2. **Mid-year change loop (DD-026, commits `3a8fcaa` → `3bcb945`)** — the "locked timetable
   changes" feature you described:
   - **Backend**: new `timetable_overrides` table (migration `d319882e1438`, now **23 tables**).
     A published timetable stays immutable; each in-term correction is a change row: teacher
     cover, room change, lecture swap, temporary (date-window) change, custom. Endpoints under
     `/instances/{id}`: `GET /overrides` (change list with old/new names resolved for display),
     `POST /overrides` (create, **conflict-checked** — 409 on conflict, nothing saved),
     `POST /slots/{id}/swap`, `DELETE /overrides/{oid}` (revert, kept as history), and
     `GET /overrides/available-faculty` (candidate teachers free at a day/slot, excluding the
     instance's own bookings, other active overrides, and published cross-timetable
     reservations). Validation runs the structural checker against the instance's other slots +
     published reservations; data-driven profile rules are skipped for mid-year edits.
   - **Frontend**: published instances get a **Change mode** (Wrench toggle). Click a cell →
     Apply-change editor with a change type, a **covering-teacher dropdown fed by
     available-faculty** (only teachers free at that day/slot — verified live), room picker,
     swap targets, and an optional temporary date window. A **Mid-year changes panel** beside the
     grid lists active changes with resolved old/new names and a Revert action; reverted changes
     stay in history.
   - 7 new tests (186 total): clean cover, cover rejected for the new teacher's availability,
     room change, swap, resolve/revert, change-list name resolution, available-faculty excluding
     busy teachers.
3. Earlier this session (before the change loop) the **assignment grid** and the
   **profile/constraint builder** shipped — see the previous handoff's summary if needed
   (commits `a53e69c` → `1979d9d`).

**Backend reality that matters for the product**: rooms are a shared pool — the solver assigns a
room per session from the subject's `requirements_json`, so a subject is taught in different
rooms across the week (matches the user's college; no fixed classroom per subject). The engine,
RBAC, exports, async generation, constraint registry, all six soft constraints, compare,
slot-override revalidation, the assignment grid, the profile builder, and the mid-year change
loop are built and tested.

---

## Open design decisions (from `documentation/design-decisions.md` — resolve these)

1. **DD-004 follow-up** — promote mail gating to a `CollegeSettings.mail_enabled` flag, or keep
   env-only? (Likely keep env-only until a college asks; but decide and record.)
2. **DD-003 follow-up** — do publish notifications need a retry queue / per-recipient opt-out /
   an admin `/notifications` endpoint? (Currently: log-and-drop.)
3. **DD-001 follow-up** — RBAC now exists (DD-021): re-point the publish mailer from
   `config_json["notification_emails"]` to real HOD-role accounts. Worth doing when the
   notifications endpoint lands.
4. **DD-018 follow-up** — the four-service compose bring-up could not bind host port 3000 on the
   dev machine (occupied by another container); the frontend image itself was verified on an
   alternate port. Next session: run the full `docker compose up` on a free 3000 and confirm
   login → dashboard in a browser, then mark DD-018 Live-verified.
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

## Next task — teacher portal (DD-022 #1), then the DD-024 batch/domain layer

1. **Teacher portal** (DD-022 #1) — `/my-schedule`: teacher sees only their slots (exports already
   accept `?faculty_id=`), exports own iCal/PDF, and a "today" card. Requires either server-side
   caller scoping on the slots read (DD-021 follow-up) or a `GET /my/schedule` endpoint — the
   design plan calls for confirming `app/router/instances.py` first. When it lands, resolve
   `timetable_overrides` by date (DD-026 follow-up) so the teacher's "today" reflects covers/swaps.
2. **DD-024 domain work** — the batch/tutorial/per-day-grid requirements the founder described.
   Design exercise first (see the DD-024 entry): verify each rule against the real college data,
   then decide the model (batch groups + parallel practicals, per-subject tutorial/practical
   flags, per-day time grids, all-active-timetable conflict reservations). Will touch
   `app/models/`, the greedy/OR-Tools solvers, the checker, and the seed. **Apply the DD-025
   posture throughout**: college-specific facts are data rows the teacher sets (system only
   suggests), never hardcoded engine logic.
3. Optional polish: CSV upload modals on resource pages; WebSocket progress for async runs; a
   `/constraints` reference catalog page (data already exposed via `GET /constraints/types`).

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

Full backend verification: `uv run python -m app.tests` (186) · scale: `scripts/full_stack_test.py`
(after a fresh seed; server must be up) · live API drive: `scripts/api_drive.py`,
`scripts/async_drive.py` (async needs ASYNC_GENERATION=true + a celery worker).

---

## Gotchas

- Postgres :5433, Redis :6379; Alembic head `d319882e1438` (`timetable_overrides`, DD-026).
  **23 tables.**
- **`npm run build` corrupts a running `next dev` `.next` cache** — after any build, kill the dev
  server, `rm -rf frontend/.next`, restart dev. Also always restart dev after pulling/committing.
- **The backend dev server runs WITHOUT `--reload`** (uvicorn started by `nohup`). After editing
  backend code, restart it manually — a stale server silently serves old routes.
- **Design decisions are tracked in `documentation/design-decisions.md`**, not in this file. Every
  new choice gets a DD-NNN entry in the same commit; the HANDOFF copies OPEN items verbatim.
- **New `Settings` fields must go in `.env.example`** in the same commit (real past miss).
- **Tests**: `uv run python -m app.tests` (not pytest). New test modules must be imported in
  `app/tests/__main__.py` and new routers must be in the conftest patch loop.
- **The auth gate is global** — every route except `/health` and `/auth/*` needs a JWT;
  `/api/v1/*` is not exempt. Role claims ride the JWT; `require_roles()` gates finer endpoints.
- **Error envelope**: every error returns `{"detail": ...}`; 422/500 add `request_id`. The CORS
  `expose_headers` exposes `X-Total-Count`/`X-Request-ID` — keep that.
- **Frontend data fetching**: all via TanStack Query (`src/hooks/use-resources.ts`); pages are
  `"use client"`. `useSearchParams` pages need a `<Suspense>` wrapper (see `/instances/compare`
  and `/generate`).
- **Scale testing lives in `scripts/`, not `app/tests/`** (DD-020). Re-baseline after engine
  changes: `scripts/seed_demo.py --wipe` then `scripts/full_stack_test.py` (server up).
- **The strategist agent** needs a fresh opencode session to appear in the `task` tool list (it
  was added mid-session); it's already loaded in current sessions. `.opencode/agents/strategist.md`.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md`.
