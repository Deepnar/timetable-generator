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

State at handoff: **209/209 tests passing** (`uv run python -m app.tests`), frontend builds
(`npm run build`), tree clean, all pushed. Both dev servers running (backend :8000, frontend
:3001) — see Gotchas if not. **The DB holds a published timetable for EVERY class** (192/192
instances — one per division — ~5400 slots) via `scripts/generate_college.py`.

**Login credentials** (TCET-style seed data, 12 departments, 16 classes each — FE/SE/TE/BE × A-D):
`admin@example.com` / `admin123` (admin) · **teacher: the seed now provisions a login whose
email is a real Faculty row's email** — check the "teacher login:" line printed at seed time
(currently `comp.1@tcet.edu.in` / `teach123`, R.R. Sedamkar) · `student1@tcet.edu.in` /
`teach123` (student, linked to group COMP-FE-A) · `hod@tcet.edu.in` / `teach123` (HOD).
The seed force-resets portal passwords on re-seed, so the printed credentials are always
truthful.

**This session shipped the final proper seed AND the full-project security audit (DD-029):**

1. **Full-college timetable** (`scripts/generate_college.py`, `3ac77ab`) — the founder's
   end-of-project goal: generate + publish a timetable for the entire college. One
   whole-department instance per department (best-wins variation), all semesters/divisions at
   once. Ran clean: **12/12 departments published, ~5400 slots**. Options `--only`, `--dry-run`,
   `--clear-locks`. Note: a killed run leaves a Redis generation lock for the 600s TTL —
   `--clear-locks` deletes them when safe.
2. **Security audit (DD-029, commits `a4be957` → `35ce0cf`)** — a read-only deepscan by the
   v4-pro subagent over the whole codebase (the available grok-4.5 agent is vision-only and
   cannot read code). It found the project's biggest real gap: the global auth gate
   **authenticated but never authorized** — only 4 endpoints used `require_roles`, so any
   logged-in teacher/student could do admin things (CRUD, generate, publish, reset, settings,
   audit), and public self-registration granted admin. **All remediated + regression-tested:**
   - **C-1** register now hardcodes `STUDENT` (no role field; admin provisions via `/auth/users`).
   - **C-2/C-3** every resource router is role-gated (admin+hod, or admin-only for
     constraints/settings/reset/audit).
   - **C-4** `/health` no longer leaks the raw DB exception.
   - **H-2** passwords 8–128 chars. **H-4** generation 500s are generic (detail on `error_log`).
     **H-5** DB URLs via `sqlalchemy.engine.URL`. **H-6** CSV uploads capped 10 MB / 50k rows.
   - **M-1** `POST /generate` rate-limited per IP. **M-2** security headers middleware.
     **M-5** docs/OpenAPI hidden in production (`SHOW_DOCS`/`ENV`). **M-4** frontend `getToken()`
     clears expired JWTs.
   - 4 new security-regression tests (209 total). Accepted-not-fixed (M-3 cookie auth, M-7
     psycopg2-binary, M-8 Next/React patch bumps) are tracked as DD-029 follow-ups.
3. Earlier this session: the **registration page** (DD-028, `75fd24d` → `f0b99b7`) — see the
   prior handoff.
4. **Realistic per-class timetables** (commits `8558ba7` → `d11107c`) — the founder's review of
   the first college-wide run surfaced several issues, all fixed:
   - **Merged years**: whole-department instances put FE/SE/TE/BE in one grid. The real bug was
     `_build_sessions` filtering assignments by subject only — every division sharing a subject
     was scheduled. It now also filters by the profile's group resources, and the seed creates
     **16 per-class DIVISION profiles per department** (one per division). `generate_college`
     publishes **192 instances — one clean timetable per class** (~28 sessions each, realistic contact hours).
   - **Dash-only cells**: grid/editor lookups capped at 200 rows but the college has
     hundreds of subjects — past row 200 everything resolved to nothing. The
     pagination cap is 1000 and the frontend fetches at it.
   - **Morning holes / phantom violations / missing lunch label** (fixed this pass):
     faculty were shared across classes, so publishing one reserved teachers that blocked
     others' mornings; the violation counter miscounted 2h lab blocks; and the grid showed
     no lunch. Now: dedicated per-class faculty teams (176/dept), a LUNCH BREAK row in the
     grid, per-block violation counting, and class labels on the instances list. All 192
     classes place slots 1-4 every day with 0 warnings / 0 violations.
   - **Empty days / 8:00–11:30 display / class model**: already fixed earlier this session
     (`8558ba7` → `999795b`) — see the previous handoff's item 4.

**Backend reality that matters for the product**: rooms are a shared pool — the solver assigns a
room per session from the subject's `requirements_json`, so a subject is taught in different
rooms across the week (matches the user's college; no fixed classroom per subject). The engine,
RBAC, exports, async generation, constraint registry, all six soft constraints, compare,
slot-override revalidation, the assignment grid, the profile builder, the mid-year change loop,
both role portals, two-channel notifications, the date-resolution day layer, registration, the
full-college timetable, and the security remediation are built and tested.

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
   (3) the change loop (room change + cover + notifications). **#1 shipped for both roles** and
   **#2 shipped**: `GET /my/schedule` / `/my/timetable` accept `?date=` and resolve mid-year
   changes for that date (a permanent cover applies, a TEMP window wins inside its dates, a SWAP
   exchanges faculty/room), so "is there class on date X" and the day card are truthful. Remaining:
   the change-loop notifications were already built (DD-027); WebSocket push and the student
   "today" parity are polish.
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
    endpoints + change-mode UI with candidate-teacher picker and a revertible change list) and
    the **date-resolution layer** is now shipped too (`app/services/override_resolver.py`;
    `/my/schedule` + `/my/timetable` accept `?date=` and `/my/today` resolves overrides against
    today — a TEMP window wins inside its dates, a permanent cover wins outside it, a SWAP
    exchanges faculty/room). Remaining: a college flag to gate whether changes are allowed on
    locked timetables at all, and surfacing effective dates in the admin change list.
12. **Registration + auth** — **email+password register page shipped (DD-028)**, and the
    security audit (DD-029 C-1) locked self-registration to the **student** role (no role field,
    least privilege). Elevated roles are admin-provisioned via `/auth/users`. Still OPEN: whether
    to gate registration (invite code) before launch and the **Google OAuth** question (deferred
    until a college asks, see DD-028).
13. **Final proper seed** — the **full-college timetable is generated and published**
    (`scripts/generate_college.py`, 192/192 classes, ~5400 slots in the local DB). Remaining:
    replace the TCET-style *demo* data with the college's **real** data before public launch
    (decide a source), then re-run the seed + `scripts/full_stack_test.py` at whole-college scale.
14. **DD-027 follow-up** — the two-channel notification system (in-app + email) is shipped for
    publish and mid-year changes. Remaining: an email retry queue (DD-003), per-recipient
    opt-out, re-sending when a change is reverted, a college flag to disable the in-app channel,
    and WebSocket/SSE push if the product ever needs live delivery.
15. **DD-029 follow-up** — the security audit is remediated and regression-tested. Accepted
    items to revisit before public launch: switch JWT storage to httpOnly cookies (M-3),
    evaluate `psycopg2-binary` in the prod image (M-7), bump Next/React patch levels and run
    `npm audit` (M-8).

---

## Next task — pre-launch hardening and real-data rollout

The full-college timetable and the security audit (DD-029) are done; all of DD-022, DD-026,
DD-027, and DD-028 are shipped. Remaining, in order:

1. **DD-029 pre-launch items (OPEN 15)** — httpOnly-cookie JWT storage (M-3), `psycopg2-binary`
   vs source build in the prod image (M-7), Next/React patch bumps + `npm audit` (M-8), and an
   invite-code/registration gate decision.
2. **Real data rollout (OPEN 13)** — replace the demo seed with the college's real data (source
   TBD) and re-run `scripts/seed_demo.py --wipe` + `scripts/generate_college.py --instances 3`
   + `scripts/full_stack_test.py` to re-baseline at whole-college scale.
3. Optional polish: CSV upload modals; WebSocket/SSE push; a `/constraints` reference catalog
   page; a college flag to gate changes on locked timetables (DD-026); the DD-024 batch/
   tutorial/per-day-grid domain layer (verify against real data first, under the DD-025 posture).

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

# seed the TCET-style dataset (12 depts / 16 classes each = 192 groups / 492 subject streams / 324 rooms / 204 profiles)
# NOTE: prints a "teacher login:" line with the portal teacher credential
uv run python -m scripts.seed_demo --wipe

# generate + publish a timetable for the ENTIRE college (all 12 departments)
uv run python -m scripts.generate_college --instances 3   # ~6-10 min; --clear-locks if a killed run left a Redis lock

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

- Postgres :5433, Redis :6379; Alembic head `92a486f10bf9` (`app_notifications`, DD-027; prior
  `9fe4f7187298` added `student_groups.student_email`). **24 tables.**
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
  `/api/v1/*` is not exempt. **Role gates (DD-029)**: resource routers are admin+hod, and
  constraints/settings/reset/audit are admin-only; `/my/*` and `/notifications/*` stay
  per-endpoint. Public self-registration creates a **student** account only.
- **Security posture (DD-029)**: security headers set on every response; `/docs` + OpenAPI hidden
  when `SHOW_DOCS=false`/`ENV=production`; `POST /generate` is per-IP rate-limited; CSV uploads
  capped at 10 MB / 50k rows; `/health` never returns the raw DB error; passwords require 8–128
  chars. Accepted-not-fixed: JWT in localStorage (M-3), `psycopg2-binary` (M-7), Next/React patch
  bumps (M-8).
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
