# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, commit rules.

> ## ⚠️ START HERE: `documentation/system-audit-and-plan.md`
>
> An independent audit (15 Aug 2026) found the engine is **solving the wrong problem correctly**.
> That document is the current source of truth for what is wrong and what to build, in order.
> The decision record is **DD-031** in `documentation/design-decisions.md`.

---

## The one-paragraph situation

**Phase 3b (constraint editing) is COMPLETE; Phase 4's engine work is DONE with the headline
metric: zero unplaced across all 11 COMP divisions (was 10), 0.63s total, 256 tests green,
pushed.** Phase 3b: INVARIANT/INSTITUTIONAL tiering (DD-042, migration `c9d4e8f2a6b0`),
institutional rules fire only from rows, `GET /constraints/types` returns tier + config
JSON-schema, registry/enum parity assertion, college facts in `CollegeSettings.config_json`
(DD-043, `--codes` flag, config_json merge). Phase 4: **DD-044** — the cell parser reads lab
faculty positionally (the glossary gate dropped every pair's second initial; "IIS MP 608" was
misparsed as subject MP, inflating demand and deleting IIS lectures) and single-teacher batch
pairs merge into one session; **A6** — fail-fast `is_valid`, most-constrained-first ordering,
best-scoring-distinct-attempt quality default, committed-slot index; **A4** — faculty caps
include published load. **Measured: unplaced 10 → 0**; hours metric 3/53 outside ±1 (all
PROJECT — the honest no-mentor gap). Site republished 11/11 with zero unplaced.

**Cohort profiles and LNS are deferred (DD-045), gated on real needs:** every year's divisions
differ in their grids (SE: breaks 4/5/none; TE: 4/3; BE-A Saturday+ACTIVITY_ONLY vs B/C none),
so the cohort requires **per-group grid parameters** threaded through greedy, the checker,
OR-Tools, the importer, and the resolver — a genuine engine change — while the phase's done-when
is already met per division and the audit's other cohort motivations (room competition, caps)
are inert until the college supplies real numbers. **Next up: Phase 5 — Prove it.**

**On "are the website timetables good now?"** — placement-complete and honest, but Phase 5
(fidelity scorer + synthetic problem generator) is the honest yardstick, and rendering
correctness (Phase 6 C1–C4) is the only thing worth eyeballing today.

---

## Work in order — each item says where to look and what "done" means

Full detail per phase is in `system-audit-and-plan.md` **Part E**. Findings are cross-referenced as
**[A*n*]** (engine), **[B*n*]** (bugs/security), **[C*n*]** (frontend), **[D*n*]** (generality).

> **Scope rule for Phases 0–5: COMP only.** The importer defaults to `--codes COMP`; re-admit
> IT with `--codes COMP,IT` at Phase 5 (see [D5]).

### Phase 5 — Prove it, and prove it stays proved (4 days) ← **start here**

1. **Fidelity scorer as a library** — the Phase 3 exit metric (weekly hours per (subject,
   division) within ±1 of the published grid) as a reusable scorer with the metrics table from
   **[A8]**; the handoff's "Reproducing every number" script is the seed of it.
2. **Golden tests** — regenerate every division, score, fail CI on regression.
3. **Synthetic problem generator** — plant a valid timetable, derive inputs from it. Any unplaced
   session is then provably a solver bug. Retire `build_synthetic_branches.py` as a scoring input.
   **[D4]**
4. **Second fixture college** with a different shape (6 slots, break at 3, 5-day, 2 batches,
   2-slot labs, no home room). CI generates both. If it needs an `app/engine/` change, overfitting
   is caught that day. **[D3]** — note: this fixture is also the natural vehicle for the
   per-group-grid parameters from DD-045 if the cohort is picked up.
5. Re-admit IT (`--codes COMP,IT`), then the rest, each gated on the suite staying green.

**Done when:** every division regenerates to the same score; a planted timetable is reproduced
exactly; the second college needs zero engine changes.

### Phase 4 — remainder (deferred by DD-045, build when needed)

1. **Per-group grid parameters** (`break_slots_by_group`, `working_days_by_group`,
   `saturday_policy_by_group`) through greedy scans, the checker's `NO_TEACHING_IN_BREAK_SLOT`,
   OR-Tools day domains, the importer, and the profile resolver.
2. **Cohort profiles** — one generation per (department, year); decide the artifact shape
   (cohort instance vs solve-once-slice-per-division) with the frontend (Phase 6).
3. **Construct-then-repair LNS** (A11) — greedy constructs; CP-SAT re-optimises small
   neighbourhoods. **Never post-filter a CP-SAT answer.**

**Done when:** zero unplaced across the COMP cohort, under a minute per cohort (already true per
division; the cohort changes the *artifact*).

### Phase 6 — Frontend (4–6 days)

**Confirmed on the live site (16 Aug 2026, COMP-SE-A/B instance pages):** the two visible
grid defects are exactly C2 + C3/C4, verified in code — the backend data is correct:

1. **Print stylesheet** — A4 landscape, one division per page. **[C1]**
2. **Redesign the parallel-batch cell** — `CellStack` (`TimetableGrid.tsx:194`) stacks 4 lab
   batches in a 76px row (`TimetableGrid.tsx:87`); text clips and batch badges overlap
   (COMP-SE-A Mon/Tue/Wed 08:30, Thu 14:30). A 2×2 split layout or auto-grown row height.
   Note: DD-044 merged pairs record the representative batch on the slot — show the full pair
   from `window_key`/`batch_list`. **[C2]**
3. **Real break + slot times reach the grid** — `breakAfterSlot={4}` is **hardcoded**
   (`instances/[id]/page.tsx:153`), so the break row is wrong for every division whose break is
   not slot 4 (SE-C: 5, TE-B: 3, BE-*: 6), and the break slot renders as an **empty unlabeled
   row** because `slotTime` is derived from *placed* slots (`use-grid-sessions.ts:84-95`) —
   nothing is placed in the break slot, so its label falls back to a bare `"4"`. The backend
   already has the truth (`break_slots` + verbatim `slot_times` per profile) but the instance
   page never fetches profile params. Fix: `breakSlots: number[]` prop + required `slotTime`,
   fed from the profile's params. **[C3, C4]**
4. **Constraint editor UI** — the Phase 3b done-when: `GET /constraints/types` returns
   tier + config JSON-schema per type; the editor renders a form from it and writes
   `hard_constraints` rows (profile_id NULL for college defaults) and `PUT /settings` facts
   (config_json merges). Include the DD-039 toggle affordance.
5. Post-generation review: score breakdown, unplaced list **with reasons** (the checker already
   produces them and they are discarded), diff vs published. **[C6]**
6. Accessibility: grid semantics, keyboard nav, non-colour subject encoding; move route protection
   from `ProtectedShell` to middleware. **[C7]**

### Phase 7 — Security hardening (2 days)

Central deny-by-default role table; role from the DB not the JWT (`utils/auth.py:100`); one DB
session per request (`main.py:150` + `:179` open two more); route-resolved auth exemption instead of
the `/auth/` string prefix (`main.py:141`); login rate limiting fails **closed**; startup assertions
on `SECRET_KEY` length and `CORS_ORIGINS != "*"`. **[B-MED-3 … B-LOW-6]**

---

## Open design decisions (from `design-decisions.md` — carry forward)

- **DD-045 follow-up** — per-group grid parameters are the cohort prerequisite; the artifact-
  shape choice (cohort instance vs slice-per-division) needs the frontend's input. Gated on the
  college enabling caps or asking for the per-year document.
- **DD-044 follow-ups** — merged pair coverage: only the representative `batch_number` reaches
  `TimetableSlot` (the full pair rides on the session's `batch_list`); Phase 6's cell renderer
  should show the pair. Confirm with the registrar whether BE-A's single-teacher pairs are merged
  sessions or sequential ones.
- **DD-043 follow-up** — synthesized lab `min_capacity: 40` and synthetic faculty caps
  (`max_hours_per_week=30`, `max_hours_per_day=8`) are still adapter constants (inert — no
  constraint row enables the caps); a future pass can move them into the facts document.
- **DD-042 follow-up** — profile-level override semantics for a college-default rule (a profile
  row currently *adds to* the default; it cannot switch a default off for one profile alone).
- **DD-037 follow-up** — PROJECT (BE-A/B/C) has grid cells but no named teacher, so no competency
  exists and even `--fill-gaps` cannot assign it. The college must supply project mentors.
- **DD-038 follow-up** — `preference_weight` on `faculty_subject_competency` is collected but not
  yet used by the least-loaded picker; a UI to manage competencies is a Phase 6/3b item.
- **DD-039 follow-up** — the institutional toggle (re-enabling capacity/caps) works via rows; the
  constraint editor UI (Phase 6) is the affordance.
- **DD-034 follow-up** — the real grids sometimes move the break by day (COMP-SE-A: slot 4 Mon-Wed,
  slot 5 Thu-Fri); the single `break_slots: [int]` picks the modal slot. Per-(day, slot) break data
  is a future refinement.
- **DD-032 follow-up** — shared teaching (two teachers, one subject, `load_share` 0.8/0.2) is
  blocked by the unique index; the solver ignores `load_share` today. If wanted later, needs its own
  mechanism, not duplicate rows.
- **DD-004 follow-up** — promote mail gating to a `CollegeSettings.mail_enabled` flag or keep
  env-only.
- **DD-003 follow-up** — email notifications need a retry queue / per-recipient opt-out.
- **DD-001 follow-up** — point the publish mailer at real HOD-role accounts now RBAC exists.
- **DD-018 follow-up** — full `docker compose up` on free port 3000; login→dashboard in a browser;
  mark DD-018 Live-verified.
- **DD-020 follow-up** — wire seed + battle test into CI or keep local; cadence after engine changes.
- **DD-021 follow-up** — teacher/student read-scoping on list endpoints.
- **DD-022 follow-up** — WebSocket push + student "today" parity are polish.
- **DD-023 follow-up** — block-level overrides (moving one slot of a merged lab block leaves its
  siblings behind).
- **DD-024 (OPEN)** — the college's real rules; verify each against real data, then design. Superseded
  in priority by DD-031's phases, which cover the same ground (lab windows, one-lab-per-day, per-day
  grids).

## Working agreements for this plan

- **Model before solver.** Do not optimise or replace a solver that is being asked the wrong
  question. Phases 1–2 changed the output shape; Phase 3 made the input honest; Phase 4 makes it
  complete.
- **Every phase ends with a measured number**, not a description. The metrics table above is the
  scoreboard; re-run it and put the delta in the commit body.
- **No new synthetic people.** More fake teachers make bugs unattributable. See **[A9, D4]**.
- **No college constants in `app/engine/`.** They belong in the institution facts document. **[D2]**
- **Commits**: many small focused ones, impersonal voice, staged in logical chunks (`AGENTS.md`).
- **Docs in the same change**: `timetable-generator-architecture.md` §3 schema / §4 endpoints /
  §5 engine / §8 params, plus `plan.md` + `progress.md` checkboxes. New decisions → DD-046 onward in
  `design-decisions.md`.

## Reproducing every number in this handoff

```bash
# zero-unplaced + timing across the 11 COMP divisions (Phase 4 exit metric)
.venv/bin/python - <<'PY'
import time
from app.database import SessionLocal
from app.engine.profile_resolver import ProfileResolver
from app.engine.solvers.greedy_solver import GreedySolver
from app.models.profiles import TimetableProfile
from sqlalchemy import select
db = SessionLocal()
total = 0; t0 = time.time()
for prof in db.scalars(select(TimetableProfile).order_by(TimetableProfile.id)).all():
    solver = GreedySolver(db=db, profile=ProfileResolver(db).resolve(prof.id), instance_id=9999)
    solver.solve()
    total += solver.unplaced_count
print(f"unplaced: {total}  time: {time.time()-t0:.2f}s")
db.close()
PY

# weekly hours per (subject, division) vs the published grid (Phase 3 exit metric)
.venv/bin/python - <<'PY'
import json
from app.database import SessionLocal
from app.models.subject_assignments import SubjectAssignment
from sqlalchemy import select
from app.models.groups import StudentGroup
from app.models.subjects import Subject
db = SessionLocal()
subjects = json.load(open("info/import/subjects.json"))["subjects"]
code_to_name = {(s["department_code"], s["semester"], s["code"]): s["name"] for s in subjects}
comp = [t for t in json.load(open("info/import/timetables.json"))["timetables"]
        if t["group_name"].split("-")[0] == "COMP"]
grid = {}
for t in comp:
    for c in t["cells"]:
        k = c.get("kind")
        if k in ("LECTURE", "TUTORIAL", "ACTIVITY") and c.get("subject"):
            grid[(t["group_name"], c["subject"])] = grid.get((t["group_name"], c["subject"]), 0) + 1
assigns = {}
for a in db.scalars(select(SubjectAssignment)).all():
    if a.batch_number is not None: continue
    g = db.get(StudentGroup, a.group_id); s = db.get(Subject, a.subject_id)
    if g and s: assigns[(g.name, s.name)] = assigns.get((g.name, s.name), 0) + (a.weekly_hours or 0)
bad, total, seen = [], 0, set()
for t in comp:
    sem, dept = t["semester"], t["group_name"].split("-")[0]
    for (gname, code), grid_h in sorted(grid.items()):
        if gname != t["group_name"]: continue
        name = code_to_name.get((dept, sem, code), code)
        if (gname, name) in seen: continue
        seen.add((gname, name)); total += 1
        if abs(grid_h - assigns.get((gname, name), 0)) > 1: bad.append((gname, name, grid_h))
print(f"outside +-1: {len(bad)}/{total}", bad)
db.close()
PY

# institution facts document + registry/enum parity
.venv/bin/python -c "from app.database import SessionLocal; from app.services.settings_service import get_settings; print(get_settings(SessionLocal()).config_json)"
.venv/bin/python -c "from app.engine.constraint_registry import assert_registry_enum_parity; assert_registry_enum_parity(); print('parity OK')"
```

## How to run

```bash
uv run alembic upgrade head
uv run python scripts/generate_tcet_import.py      # refresh info/import/*.json from the markdown pack
uv run python -m scripts.import_tcet --wipe --fill-gaps   # seed Postgres (--codes COMP default)
uv run python -m scripts.generate_college --instances 1 --clear-locks   # publish all (~2 min)
uv run python -m app.tests                         # 256 tests
cd frontend && npm run typecheck                   # NOT npm run build
```

Backend :8000, frontend :3001, admin@example.com / admin123. Postgres on host port **5433**.

> **Re-seed with `--fill-gaps`** — the importer re-seeds the college-default institutional
> constraint rows after `--wipe`, seeds the institution facts document (missing keys only,
> registrar edits win), and reports data gaps by default. `parse_cell` lives in
> `scripts/cell_parser.py`; change the parser → regenerate (`generate_tcet_import.py`) →
> re-import → re-publish.

## Gotchas (carried forward — still true)

- **alembic `env.py` uses `hide_password=False`** — do not revert; the masked URL broke migrations.
- **`npm run build` corrupts a running `next dev`** — use `npm run typecheck`. If dev hangs on
  "Checking session…": kill it, `rm -rf frontend/.next`, restart.
- **Backend dev server runs WITHOUT `--reload`** — restart manually after backend edits
  (`kill` the uvicorn pair, `nohup uv run uvicorn app.main:app --port 8000 > /tmp/timetable-api.log 2>&1 &`).
- **Tests are `uv run python -m app.tests`, not pytest.** New modules register in
  `app/tests/__main__.py`. When a new router is touched by the SQLite tests, add it to the patch loop
  in `app/tests/conftest.py` or it will hit Postgres.
- **New `Settings` fields must go in `.env.example`** in the same commit.
- **Postgres NULLs are distinct** — a unique index on nullable columns does NOT dedupe NULL rows.
  Use `COALESCE(col, 0)` in the index expression (see `e6a1b7c3d9f2`).
- **Lab windows are `(group, period)`** — `subject_assignments.period_number` is group-scoped
  (A1); two subjects in one window share a period. **Single-teacher batch pairs merge (DD-044)**:
  the merged member records the representative batch on the slot; `batch_list` carries the pair.
- **Institutional rules fire only from rows** (Phase 3b, DD-042) — tests rely on the college-
  default rows `seed_minimal` inserts (mirroring migration `c9d4e8f2a6b0`). Capacity and faculty
  caps stay off unless a `hard_constraints` row enables them (DD-039) — and now count PUBLISHED
  load (A4).
- **`CollegeSettings.config_json` is the facts document** (DD-043) — `PUT /settings` MERGES
  key-by-key; the importer seeds `scheme_hours`/`year_strengths`/`batches_per_year` when missing.
- **The feasibility report hard-fails oversubscribed runs with a 409** (DD-040).
- **OR-Tools window co-location uses presence indicators** (DD-041); `unplaced_count` counts
  committed sessions; the faculty caps + SAME_SUBJECT_SAME_DAY parity honour the row gating.
- **`GET /constraints/types` shape changed in Phase 3b** — hard/soft are lists of
  `{type, tier, config_schema}` objects, not plain strings.
- **`is_valid` is fail-fast** (Phase 4 A6) — `check_all` still collects the full report;
  diagnostics that need every reason use `check_all`. Validators read indexed committed-slot
  buckets via the context; direct validator calls without a context fall back to scanning.
- `scripts/seed_demo.py` is a fabricated demo; `scripts/seed_tcet.py` is superseded by the importer.
