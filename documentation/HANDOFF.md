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

State at handoff: **196/196 tests passing** (`uv run python -m app.tests`), frontend builds
(`npm run build`), tree clean, all pushed. Both dev servers running (backend :8000, frontend
:3001) — see Gotchas if not.

**Login credentials** (TCET-style seed data, 12 departments, 204 rooms / 576 subjects etc.):
`admin@example.com` / `admin123` (admin) · **teacher: the seed now provisions a login whose
email is a real Faculty row's email** — check the "teacher login:" line printed at seed time
(currently `comp.1@tcet.edu.in` / `teach123`, R.R. Sedamkar) · `student1@tcet.edu.in` /
`teach123` (student, linked to group COMP-S1-A) · `hod@tcet.edu.in` / `teach123` (HOD).
The seed force-resets portal passwords on re-seed, so the printed credentials are always
truthful.

**This session shipped BOTH role portals (DD-022 #1) and recorded the auth + final-seed notes:**

1. **Teacher portal** (previous session, `df84d4c` → `02172dc`) — `/my-schedule`: Today card,
   weekly grid, own exports; `GET /my/schedule`, `/my/today`, `/my/export`; identity by
   email→Faculty match; role-based login redirect.
2. **Student portal** (this session, `bec4833` → `deb36bc`) — `/my-timetable`, the mirror:
   - **Backend**: new `student_groups.student_email` column (migration `9fe4f7187298`, still 23
     tables) links a student login to a group. `GET /my/timetable` returns that group's
     published slots with subject/room/group/**faculty** names resolved; `/my/today` and
     `/my/export/{pdf,csv,ical}` now serve students too (their group's slots / filtered
     export). `MySlot` gained `faculty_name` so the student grid shows the teacher.
   - **Frontend**: `/my-timetable` — Today card, the group's read-only grid, own iCal/PDF.
     Role-based login already routed students there. Seed links the demo student login to the
     first group and force-resets portal passwords.
   - 5 new tests (196 total): own-group timetable with names, unmatched-student empty, teacher↔
     student role gates, student group iCal export, student `/my/today`.
3. **Notes recorded** (founder detail log rows 14–16, OPEN items 12–13): registration UI +
   Google OAuth question; final proper seed for the entire college.

**Backend reality that matters for the product**: rooms are a shared pool — the solver assigns a
room per session from the subject's `requirements_json`, so a subject is taught in different
rooms across the week (matches the user's college; no fixed classroom per subject). The engine,
RBAC, exports, async generation, constraint registry, all six soft constraints, compare,
slot-override revalidation, the assignment grid, the profile builder, the mid-year change loop,
and both role portals are built and tested.

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
   identity once the frontend defines which views each role needs. The teacher portal (`/my/*`)
   is the reference pattern for caller-scoped reads.
7. **DD-022 follow-up** — build order for the teacher-workload roadmap: (1) teacher self-service
   schedule + own-slot exports, (2) the `timetable_overrides` date-resolution layer + day card,
   (3) the change loop (room change + cover + notifications). **#1 shipped** (`/my/schedule`
   portal: Today card, weekly grid, own exports; role-based login redirect). Next: the student
   portal, then the date-resolution `GET /my/today` layer resolving overrides by date (#2), then
   the change-loop notifications (#3).
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
12. **Registration + auth (OPEN)** — the backend has `POST /auth/register` (public, defaults to
    `admin` role) but the frontend is login-only. A register page/form is needed; whether it
    should also offer **Google OAuth** is undecided (founder flagged it as a question). Decide
    the auth story (email+password vs Google) and record it before the teacher/student portals
    ship, since those roles need a way for users to get accounts without admin provisioning.
13. **Final proper seed (OPEN)** — before launch, re-seed the DB with real college data and
    generate the timetable for the **entire** college (not the demo seed), per the founder. This
    is end-of-project polish; the seed scripts live in `scripts/` (DD-020) and the engine
    already scales to whole-department runs. Decide a source for the real data.

---

## Next task — the date-resolution day layer (DD-022 #2)

Both role portals (DD-022 #1) are done. Remaining, in order:

1. **Date-resolution layer** (DD-022 #2 / DD-026 follow-up) — `GET /my/today` should resolve
   `timetable_overrides` by the real date: a TEMP cover wins inside its `date_from`/`date_to`, a
   permanent cover wins outside it, and a covered slot is hidden while its cover applies. This is
   what makes "is there class on date X" and the day card truthful. Needs a date-aware slots read
   shared by `/my/*`, the change list, and the grid.
2. **Change-loop notifications** (DD-022 #3) — hooks on override/cover creation → SMTP (DD-003/4
   follow-ups become relevant); room change + cover notifications reuse `mail_service`.
3. Optional polish: register page/form + the Google OAuth decision (OPEN 12); CSV upload modals;
   WebSocket progress for async runs; a `/constraints` reference catalog page.

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
# NOTE: prints a "teacher login:" line with the portal teacher credential
uv run python -m scripts.seed_demo --wipe

# frontend on :3001 (port 3000 is owned by an unrelated container on this machine)
cd frontend && npm install && npm run dev -- -p 3001 &

# screenshots: node scripts/screenshot.mjs  (real login + per-page capture → /tmp/opencode/shots)
# verify visually via the vision skill (mimo for routine checks)
```

Full backend verification: `uv run python -m app.tests` (191) · scale: `scripts/full_stack_test.py`
(after a fresh seed; server must be up) · live API drive: `scripts/api_drive.py`,
`scripts/async_drive.py` (async needs ASYNC_GENERATION=true + a celery worker).

---

## Gotchas

- Postgres :5433, Redis :6379; Alembic head `9fe4f7187298` (`student_groups.student_email`,
  the student-portal link; prior `d319882e1438` added `timetable_overrides`). **23 tables.**
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
