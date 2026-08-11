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

State at handoff: **177/177 tests passing** (`uv run python -m app.tests`), frontend builds
(`npm run build`), tree clean, all pushed. Both dev servers should be running (backend :8000,
frontend :3001) — see Gotchas if not.

**Login credentials** (TCET-style seed data, 12 departments, 204 rooms / 576 subjects etc.):
`admin@example.com` / `admin123` (admin) · `teacher1@tcet.edu.in` / `teach123` (teacher) ·
`student1@tcet.edu.in` / `stud123` (student) · `hod@scale.edu.in` / `pass123` (HOD).

**This session** built the frontend through Phase 2 of the design plan
(`documentation/frontend-design-plan.md` — the qwen3.8-max strategy + library notes, restored
verbatim after an earlier session wrongly replaced it):

1. **Phase 1 foundation** (commits `e56eb2b`, `70da0a2`) — deps (Radix/shadcn-style kit, TanStack
   Table v8 + Query, Recharts, Sonner, lucide, CVA/tailwind-merge/animate); **Next bumped 14.2.15 →
   14.2.35** (critical advisories); design tokens (indigo `#4338CA` accent, Fraunces/Inter/
   JetBrains Mono, warm canvas `#F5F3EF`, radius/shadow scale); hand-authored `src/components/ui/`
   kit; sidebar shell + topbar + role-filtered nav; TanStack DataTable (server-side
   page/sort/search) + query hooks (2s generation-status polling, optimistic slot override);
   Providers (QueryClient + Sonner).
2. **Phase 1 pages** (commit `c22ebe9`) — login split-screen, dashboard (stat cards, colored
   Recharts bars, runs list), and Rooms/Faculty/Groups/Subjects on a reusable `ResourcePage`
   (Sheet create/edit drawer, AlertDialog delete, badges, avatar initials, toasts).
3. **Ink sidebar + warm table header** (commit `171f6bf`) — reused the login panel's ink
   `#1C1917` for the sidebar and tinted table headers, per user "subtle darkness" feedback.
4. **Server-side search** (commit `33fb67c`) — `?search=` on rooms/faculty/groups/subjects lists.
5. **Drill-down navigation** (commit `792d4c4`) — category tiles (clickable counts) + facet rail
   + breadcrumbs + URL state; `useFacetCounts` probes X-Total-Count per value. Surfaced a real
   backend bug: **CORS never exposed `X-Total-Count`/`X-Request-ID`** (commit `b501023`) so every
   frontend list total silently fell back to page length.
6. **Phase 2 scheduling read path** (commits `fe3d973`→`09a61a4`) — `GET /instances/` list
   endpoint (new), `/generate` (profile picker + run cards with 2s polling), `/instances`
   (all-instances table), `/instances/[id]` (**TimetableGrid**: pure-CSS day×slot grid with
   subject-hued color coding, row-spanning lab blocks, faculty/room/group per cell,
   PDF/CSV/iCal/Select/Publish), and `/exports` hub.
7. **Teacher-workload roadmap** (commits `f550405`, `b4d4271`) — **DD-022**: product positioned
   "for teachers"; the strategist brief recommends (1) teacher self-service schedule + own-slot
   exports, (2) a date-aware `timetable_overrides` layer + day card, (3) a change loop (room
   change + cover + notifications). See the ADR log.

**Backend reality that matters for the product**: rooms are a shared pool — the solver assigns a
room per session from the subject's `requirements_json`, so a subject is taught in different
rooms across the week (matches the user's college; no fixed classroom per subject). The engine,
RBAC, exports, async generation, constraint registry, and all six soft constraints are built and
tested.

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

---

## Next task — finish the scheduling surfaces, then the teacher portal (DD-022)

Phase 2's read path is done. Remaining, in the recommended order:

1. **Compare mode** (`/instances/compare?a=&b=`) — two synced TimetableGrids + a diff list; reuse
   the existing grid. Backend already supports selecting/publishing; add a compare endpoint only
   if the diff can't be computed client-side from the two slot lists.
2. **Slot override UI** — click a cell → popover (day/slot/room/faculty) → debounced revalidate →
   Save when clean. Backend `PATCH /instances/{id}/slots/{slotId}` exists and revalidates
   (returns 409 on conflict). Needs the revalidate result surfaced to the UI; a
   `POST .../revalidate` endpoint may be added to wrap `_revalidate_slot`.
3. **Assignment grid** (`/assignments`) — subjects × groups matrix with faculty per cell
   (backend `subject_assignments` CRUD exists).
4. **Profile & constraint builder** (`/profiles`, `/profiles/[id]`) — tabs, resource shuttles,
   param fields, constraint rows.
5. **Teacher portal** (DD-022 #1) — `/my-schedule` (teacher sees only their slots, exports own
   iCal/PDF), then the date-aware overlay + day card (#2), then the change loop (#3).
6. Optional polish: CSV upload modals on resource pages; WebSocket progress for async runs.

Keep the docs in sync (architecture §4.1/§4.2/§9, plan.md, progress.md) and record any new
decision in `design-decisions.md` (e.g. the revalidate-endpoint shape, the compare endpoint
decision).

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

Full backend verification: `uv run python -m app.tests` (177) · scale: `scripts/full_stack_test.py`
(after a fresh seed; server must be up) · live API drive: `scripts/api_drive.py`,
`scripts/async_drive.py` (async needs ASYNC_GENERATION=true + a celery worker).

---

## Gotchas

- Postgres :5433, Redis :6379; Alembic head `48c4fc85dd73` (admins.role; prior `1d8688977519`
  added placement_warning). 22 tables.
- **`npm run build` corrupts a running `next dev` `.next` cache** — after any build, kill the dev
  server, `rm -rf frontend/.next`, restart dev. Also always restart dev after pulling/committing.
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
  `"use client"`. `useSearchParams` pages are fine in the App Router client components already
  built; if a page needs `useSearchParams` and Next warns about Suspense during prerender, wrap the
  page export in `<Suspense>`.
- **Scale testing lives in `scripts/`, not `app/tests/`** (DD-020). Re-baseline after engine
  changes: `scripts/seed_demo.py --wipe` then `scripts/full_stack_test.py` (server up).
- **The strategist agent** needs a fresh opencode session to appear in the `task` tool list (it
  was added mid-session); it's already loaded in current sessions. `.opencode/agents/strategist.md`.
- Keeping `documentation/timetable-generator-architecture.md` in sync is mandatory (schema §3,
  endpoints §4, engine §5, parameters §8). Also update `plan.md`/`progress.md`.
