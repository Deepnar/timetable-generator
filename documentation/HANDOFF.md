# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, commit rules.

> ## ⚠️ START HERE: `documentation/system-audit-and-plan.md`
>
> An independent audit (15 Aug 2026) found the engine is **solving the wrong problem correctly**.
> That document is the current source of truth for what is wrong and what to build, in order.
> The decision record is **DD-031** in `documentation/design-decisions.md`.

---

## The one-paragraph situation

**Phase 3b items 1–4 — constraint tiering — is DONE (DD-042, 241 tests green, pushed).**
`STRUCTURAL_RULES` split into `INVARIANT_RULES` (physics, always-on) and
`DEFAULT_INSTITUTIONAL_RULES` (policy: SAME_SUBJECT_SAME_DAY, MAX_ONE_LAB_PER_DAY,
CROSS_DEPT_DAILY_CAP, ROOM_CAPACITY_SUFFICIENT, both faculty caps). Institutional rules fire
**only** from a profile/college-default `hard_constraints` row (`profile_id NULL` = college-wide);
migration `c9d4e8f2a6b0` seeds the three that were always-on, and the importer re-seeds them
after `--wipe`. All 8 previously-unreachable validators are now in the `ConstraintType` enum with
a **startup parity assertion** (`assert_registry_enum_parity` in `app/main.py` lifespan — the app
refuses to start if registry and enum drift). `GET /constraints/types` returns tier +
config JSON-schema per type (`CONSTRAINT_TIERS` / `CONFIG_SCHEMAS` in the registry), so a
registrar can now change "max labs per day" or turn SAME_SUBJECT_SAME_DAY off through
`POST/PUT/DELETE /constraints/hard` — no code change. OR-Tools gates its SAME_SUBJECT_SAME_DAY
parity on an active row to match greedy. Live DB migrated and verified; backend restarted.

**Remaining in Phase 3b: item 5** — move the importer's hardcoded constants into an
institution-profile document (see below). The **constraint editor UI** (the phase's done-when)
is scheduled with Phase 6's frontend work.

**Standing answer on "are the current website timetables good?"** No — and don't judge yet.
Live DB check (16 Aug 2026): 4 of the last 11 runs carry placement warnings (1–3 unplaced each);
instances 10/11 are sparse (7/19 slots). They are per-division greedy solves: faculty caps never
compose across divisions, early divisions get first pick, scoring/preference scan is off by
default. Phase 4 (cohort solving, zero unplaced) changes the output fundamentally; the honest
yardstick is Phase 5 (fidelity scorer library + synthetic problem generator — any unplaced
session then provably a solver bug). What IS worth checking now: rendering correctness
(Phase 6 C1–C4), not timetable quality.

---

## Work in order — each item says where to look and what "done" means

Full detail per phase is in `system-audit-and-plan.md` **Part E**. Findings are cross-referenced as
**[A*n*]** (engine), **[B*n*]** (bugs/security), **[C*n*]** (frontend), **[D*n*]** (generality).

> **Scope rule for Phases 0–5: COMP only.** `REAL_DATA_CODES = {"COMP"}` in
> `scripts/import_tcet.py`. 11 divisions with a real roster exercise every hard case.
> The other five branches are shape-only synthetic. Re-admit IT at Phase 5. See **[D5]**.

### Phase 3b — remainder: importer constants → institution profile (1–2 days) ← **start here**

Items 1–4 are done (DD-042, migration `c9d4e8f2a6b0`). Remaining, **[D2]**:

1. Move the importer's hardcoded constants out of `scripts/import_tcet.py` into a declarative
   institution document the college owns (profile params where scoped, else a settings/config
   file the importer reads). The list, all still hardcoded: `_scheme_hours` (L:3/T:1/P:2 fallback,
   `import_tcet.py:105`), the per-year strengths `{1:63, 2:63, 3:70, 4:60}` (`:500`), and
   `batches = 3 if year == 1 else 2` (`:749`). `lunch_break_after_slot` no longer exists (Phase 1
   removed the synthetic arithmetic); `default_block_length` already flows through
   CONTIGUOUS_LAB_SLOTS profile rows. `REAL_DATA_CODES` is a scope gate — decide whether it
   becomes an importer CLI flag or stays a constant.
2. Record the decision as **DD-043** (where the document lives: `info/import/institution.json`?
   `CollegeSettings.config_json`? profile params?) — the audit's D2 sketch shows
   `scheme_hours: {L:3,T:1,P:2}` as an institution-profile field.

**Done when:** adding a second fixture college (`fixtures/other.json`, D3) requires zero
`app/engine/` changes and only adapter changes in the importer.

### Phase 4 — Solve the cohort, not the division (5–8 days)

All 36 profiles are single-group; the college is built by publish-then-generate, so faculty caps
never compose across divisions and early divisions take the best slots.

1. Bridge first (cheap): extend `Scheduler._load_published_conflicts()` (`scheduler.py:441`) to also
   return per-faculty day/week counts, and seed the checker's counters with them. **[A4]**
2. Cohort profiles — one generation per (department, year). `greedy_solver.py:265` already filters by
   `profile_group_ids`, so this is mostly a data-shape change.
3. Fail-fast `is_valid` (`constraint_checker.py:112` runs all 14 rules even after the first failure);
   index committed slots by `(faculty|room|group, day, slot)` instead of linear scans. Cheapest large
   speedup in the codebase. **[A6]**
4. Real "most constrained first" — `greedy_solver.py:330` currently sorts on two booleans.
5. Scoring + preference scan **on by default**; always keep the best distinct attempt
   (`scheduler.py:268` currently takes the first *different* one, ignoring quality).
6. **Construct-then-repair with LNS** — greedy constructs; CP-SAT re-optimises small neighbourhoods
   (a day, a division, the blockers of an unplaced session). **Never post-filter a CP-SAT answer**:
   every rule is modelled or enforced during construction. **[A11]**

**Done when:** zero unplaced across the COMP cohort, under a minute per cohort.

### Phase 5 — Prove it, and prove it stays proved (4 days)

1. Fidelity scorer as a library (metrics table in **[A8]**).
2. Golden tests: regenerate every division, score, fail CI on regression.
3. **Synthetic problem generator** — plant a valid timetable, derive inputs from it. Any unplaced
   session is then provably a solver bug. Retire `build_synthetic_branches.py` as a scoring input.
   **[D4]**
4. **Second fixture college** with a different shape (6 slots, break at 3, 5-day, 2 batches, 2-slot
   labs, no home room). CI generates both. If it needs an `app/engine/` change, overfitting is caught
   that day. **[D3]**
5. Re-admit IT, then the rest, each gated on the suite staying green.

### Phase 6 — Frontend (4–6 days)

**Confirmed on the live site (16 Aug 2026, COMP-SE-A/B instance pages):** the two visible
grid defects are exactly C2 + C3/C4, verified in code — the backend data is correct:

1. **Print stylesheet** — A4 landscape, one division per page. **[C1]**
2. **Redesign the parallel-batch cell** — `CellStack` (`TimetableGrid.tsx:194`) stacks 4 lab
   batches in a 76px row (`TimetableGrid.tsx:87`); text clips and batch badges overlap
   (COMP-SE-A Mon/Tue/Wed 08:30, Thu 14:30). A 2×2 split layout or auto-grown row height.
   **[C2]**
3. **Real break + slot times reach the grid** — `breakAfterSlot={4}` is **hardcoded**
   (`instances/[id]/page.tsx:153`), so the break row is wrong for every division whose break is
   not slot 4 (SE-C: 5, TE-B: 3, BE-*: 6), and the break slot renders as an **empty unlabeled
   row** because `slotTime` is derived from *placed* slots (`use-grid-sessions.ts:84-95`) —
   nothing is placed in the break slot, so its label falls back to a bare `"4"`. The backend
   already has the truth (`break_slots` + verbatim `slot_times` per profile) but the instance
   page never fetches profile params. Fix: `breakSlots: number[]` prop + required `slotTime`,
   fed from the profile's params. **[C3, C4]**
4. **Constraint editor UI** — the Phase 3b done-when: `GET /constraints/types` now returns
   tier + config JSON-schema per type; the editor renders a form from it and writes
   `hard_constraints` rows (profile_id NULL for college defaults). Include the DD-039 toggle
   affordance for capacity/caps.
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

- **DD-042 follow-up (Phase 3b item 5)** — importer constants (`_scheme_hours`, strengths,
  batch counts) move to an institution-profile document; decide where (DD-043). Profile-level
  override semantics for a college-default rule are also unresolved: a profile row currently
  *adds to* the default; it cannot switch a default off for one profile alone — the UI edits
  the default row instead.
- **DD-036 follow-up** — the 9 scattered lab windows are shared-faculty data gaps: unresolved
  initials (HP vs HPK, SPS, etc.) resolve two batches of a window to the same teacher, so the
  window cannot co-locate (distinct-faculty rule). Fix via faculty resolution /
  `faculty_subject_competency` (DD-038), not in the solver. OR-Tools now *refuses* such windows
  (they show as its honest unplaced); greedy splits them.
- **DD-037 follow-up** — PROJECT (BE-A/B/C) has grid cells but no named teacher, so no competency
  exists and even `--fill-gaps` cannot assign it. The college must supply project mentors
  (a `faculty_subject_competency` row + an assignment).
- **DD-038 follow-up** — `preference_weight` on `faculty_subject_competency` is collected but not
  yet used by the least-loaded picker; a UI to manage competencies is a Phase 6/3b item.
- **DD-039 follow-up** — the institutional toggle (re-enabling capacity/caps) now works via the
  constraint editor UI (Phase 6); until then it is a profile-row insert.
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
- **No college constants in `app/engine/`.** They belong in institution-profile parameters. **[D2]**
- **Commits**: many small focused ones, impersonal voice, staged in logical chunks (`AGENTS.md`).
- **Docs in the same change**: `timetable-generator-architecture.md` §3 schema / §4 endpoints /
  §5 engine / §8 params, plus `plan.md` + `progress.md` checkboxes. New decisions → DD-043 onward in
  `design-decisions.md`.

## Reproducing every number in this handoff

```bash
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

# live-DB published-instance health (unplaced warnings / sparse instances)
.venv/bin/python - <<'PY'
from app.database import SessionLocal
from app.models.generation import TimetableGeneration, TimetableInstance, InstanceStatus
from sqlalchemy import select
db = SessionLocal()
for g in db.scalars(select(TimetableGeneration).order_by(TimetableGeneration.id.desc()).limit(6)):
    print(f"run {g.id} [{g.generation_status.value}] alg={g.algorithm_used.value} profile={g.profile_id}"
          + (f" WARNING: {g.placement_warning}" if g.placement_warning else ""))
db.close()
PY

# registry/enum parity + tier catalog (the Phase 3b invariants)
.venv/bin/python -c "from app.engine.constraint_registry import assert_registry_enum_parity; assert_registry_enum_parity(); print('parity OK')"
```

## How to run

```bash
uv run alembic upgrade head
uv run python scripts/generate_tcet_import.py      # refresh info/import/*.json from the markdown pack
uv run python -m scripts.import_tcet --wipe --fill-gaps   # seed Postgres (Phase 3: honest demand)
uv run python -m scripts.generate_college --instances 1 --clear-locks   # publish all (~2 min)
uv run python -m app.tests                         # 241 tests
cd frontend && npm run typecheck                   # NOT npm run build
```

Backend :8000, frontend :3001, admin@example.com / admin123. Postgres on host port **5433**.

> **Re-seed with `--fill-gaps`** — the importer now re-seeds the college-default institutional
> constraint rows after `--wipe` (SAME_SUBJECT_SAME_DAY / MAX_ONE_LAB_PER_DAY /
> CROSS_DEPT_DAILY_CAP, profile_id NULL), so a wiped DB keeps the migrated behaviour. Data gaps
> are reported by default and load is only invented under `--fill-gaps`.

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
  (A1); two subjects in one window share a period. The importer regenerates `assignments.json`
  from the markdown pack — run `generate_tcet_import.py` before `import_tcet.py` if you change
  the parser. Faculty initials are mapped by position within a cell's batch list (D3D4 SPS/PM →
  batch 3 = SPS, batch 4 = PM).
- **Institutional rules fire only from rows** (Phase 3b, DD-042) — tests that need
  SAME_SUBJECT_SAME_DAY / MAX_ONE_LAB_PER_DAY rely on the college-default rows that
  `seed_minimal` now inserts (mirroring migration `c9d4e8f2a6b0`); tests that want a rule OFF
  delete the rows. Capacity and faculty caps stay off unless a `hard_constraints` row enables
  them (DD-039) — see `t_faculty_cap`, `t_recurring_blackout`.
- **The feasibility report hard-fails oversubscribed runs with a 409** (DD-040) — an assignment
  asking for more sessions than the week can hold now fails before solving.
- **OR-Tools window co-location uses presence indicators** (DD-041) — the old per-pair equality
  was infeasible with 2+ room candidates and silently dropped every lab. `unplaced_count` now
  counts committed sessions, and the faculty caps + SAME_SUBJECT_SAME_DAY parity honour the row
  gating.
- **`GET /constraints/types` shape changed in Phase 3b** — hard/soft are now lists of
  `{type, tier, config_schema}` objects, not plain strings; the frontend catalog consumer must
  read `type`.
- `scripts/seed_demo.py` is a fabricated demo; `scripts/seed_tcet.py` is superseded by the importer.
