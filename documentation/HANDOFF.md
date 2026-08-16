# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, commit rules.

> ## ⚠️ START HERE: `documentation/system-audit-and-plan.md`
>
> An independent audit (15 Aug 2026) found the engine is **solving the wrong problem correctly**.
> That document is the current source of truth for what is wrong and what to build, in order.
> The decision record is **DD-031** in `documentation/design-decisions.md`.

---

## The one-paragraph situation

237 → **237 tests pass** (Phase 3 tests added; two baseline tests updated to use the new
institutional toggle). **Phase 3 — Honest demand and honest allocation is DONE.** The importer now
reads weekly hours from the published grids instead of inventing them, auto-fill is an explicit
`--fill-gaps` step that only picks qualified teachers, a new `faculty_subject_competency` table
gates every invented assignment and the solver's lab-batch fallback, `profile_resources` dropped
from 3,710 to 96 rows, every assignment carries `source` provenance, the invented-quantity
constraints (room capacity, faculty caps) are off unless a profile row re-enables them, a
pre-solve feasibility report fails loud before solving, and OR-Tools was fixed to actually place
labs on real data. Recorded as **DD-037..041**.

**Measured on the 11 COMP divisions (re-seeded with `--fill-gaps`):**

| Metric | Phase 2 | Phase 3 | Target |
|---|---|---|---|
| (subject, division) hours within ±1 of grid | flat 3h everywhere | **48 of 51** | ±1 |
| teachers over cap | 2 | **0** | 0 |
| profile_resources (FACULTY) | 3,710 | **96** | few hundred |
| assignment rows | 200 (grid + invented) | **154 GRID + 19 AUTOFILL** | GRID-only |
| constraint firing on invented number | 3 structural | **0** (toggle) | 0 |
| OR-Tools labs on COMP-TE-D | 0 | **8 of 12** (23/27 placed) | parity with greedy |
| OR-Tools labs on COMP-SE-A | 0 | **12 of 16** (29/33 placed) | parity with greedy |
| unplaced sessions (greedy) | present | still present | 0 (Phase 4) |

> The 3 hour-misses are all **PROJECT** (BE-A/B/C): the college's grid cells for PROJECT name no
> teacher at all, so no competency exists and no assignment can be made — an honest data gap the
> registrar must resolve, not a solver bug. The OR-Tools shortfall is the same story: the 4
> unplaced sessions are the shared-faculty window from DD-036 (Gaurav Nair on CG batches 3+4;
> Preksha Pareek on DS batches 1+2) — CP-SAT correctly refuses to split a window.

---

## Work in order — each item says where to look and what "done" means

Full detail per phase is in `system-audit-and-plan.md` **Part E**. Findings are cross-referenced as
**[A*n*]** (engine), **[B*n*]** (bugs/security), **[C*n*]** (frontend), **[D*n*]** (generality).

> **Scope rule for Phases 0–5: COMP only.** Set `REAL_DATA_CODES = {"COMP"}` in
> `scripts/import_tcet.py` and re-seed. 11 divisions with a real roster exercise every hard case.
> The other five branches are shape-only synthetic — they add no signal and make bugs
> unattributable. Re-admit IT at Phase 5. See **[D5]**.

> ### 🧪 Know what is real before you tune anything — **[D6]**
>
> Live DB is now **COMP-only**. Current COMP seed (with `--fill-gaps`): **41 rooms, 392 faculty
> (~59 synthetic for unresolved initials), 11 groups, 30 subjects, 173 assignments (154 GRID +
> 19 AUTOFILL), 100 competency rows**.
>
> **The only fully real artefacts are `info/import/timetables.json` (46 grids) and
> `info/import/grids.json`.** Everything else is a real *name* with an invented *quantity*.
>
> Two consequences, both load-bearing:
> 1. **No constraint may depend on an INVENTED quantity.** Done in Phase 3 (DD-039):
>    `ROOM_CAPACITY_SUFFICIENT` and both faculty caps left `STRUCTURAL_RULES`; a profile
>    `hard_constraints` row re-enables each (the INSTITUTIONAL toggle; the two faculty-cap types
>    were added to the `ConstraintType` enum so the toggle is API-reachable). Measured: they
>    rejected 0 of 31,370 candidates before, so removal changed nothing on the live data.
> 2. **Score fidelity only against `timetables.json`.** The Phase 3 exit metric — weekly hours per
>    (subject, division) within ±1 — is measured grid-vs-assignment (see the appendix script
>    below) and depends on zero invented quantities.

### Phase 3b — Make constraints editable (2 days) ← **start here**

**Eight registered validators are not in the `ConstraintType` enum**, so they are unreachable through
the API and only insertable by direct DB write — including `SAME_SUBJECT_SAME_DAY` and
`MAX_ONE_LAB_PER_DAY`, the two that contradict reality most. (Phase 3 added only the two faculty
caps; the rest of the drift is untouched.)

1. Split `STRUCTURAL_RULES` (`constraint_registry.py:43`) into `INVARIANT_RULES` (physics: double
   booking, cross-timetable) and `DEFAULT_INSTITUTIONAL_RULES` (policy: same-subject-same-day, lab
   caps, faculty caps, room capacity).
2. Institutional rules fire only from a profile/college-default row; migration seeds current
   behaviour so nothing changes silently.
3. Add all 8 missing validators to `ConstraintType`; add a **startup assertion** that the registry
   and the enum are the same set. That drift caused the gap. **[A10]**
4. `GET /constraints/types` returns tier + JSON-schema per `config_json`; build the UI editor.
5. Move every hardcoded constant out of `import_tcet.py` into institution-profile parameters
   (`REAL_DATA_CODES`, `lunch_break_after_slot=4`, `default_block_length=2`, the `{1:63,...}`
   strengths, `_scheme_hours`, `batches = 3 if year==1 else 2`). **[D2]**

**Done when:** a registrar can change "max labs per day" or the break slot in the UI, no code change.

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

1. **Print stylesheet** — A4 landscape, one division per page. **[C1]**
2. Redesign the parallel-batch cell — `CellStack` (`TimetableGrid.tsx:194`) hides the 3rd/4th batch
   behind a scrollbar in a 76px row. **[C2]**
3. `breakAfterSlot` → `breakSlots: number[]`; make `slotTime` required. **[C3, C4]**
4. Post-generation review: score breakdown, unplaced list **with reasons** (the checker already
   produces them and they are discarded), diff vs published. **[C6]**
5. Accessibility: grid semantics, keyboard nav, non-colour subject encoding; move route protection
   from `ProtectedShell` to middleware. **[C7]**

### Phase 7 — Security hardening (2 days)

Central deny-by-default role table; role from the DB not the JWT (`utils/auth.py:100`); one DB
session per request (`main.py:150` + `:179` open two more); route-resolved auth exemption instead of
the `/auth/` string prefix (`main.py:141`); login rate limiting fails **closed**; startup assertions
on `SECRET_KEY` length and `CORS_ORIGINS != "*"`. **[B-MED-3 … B-LOW-6]**

---

## Open design decisions (from `design-decisions.md` — carry forward)

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
- **DD-039 follow-up** — the institutional toggle needs a UI affordance (Phase 3b's constraint
  editor); until then re-enabling caps/capacity is a profile-row insert.
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
  §5 engine / §8 params, plus `plan.md` + `progress.md` checkboxes. New decisions → DD-042 onward in
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

# faculty utilisation / idle / over-cap (audit appendix script #3)
# greedy vs OR-Tools benchmark (audit appendix script #4) — see system-audit-and-plan.md
```

## How to run

```bash
uv run alembic upgrade head
uv run python scripts/generate_tcet_import.py      # refresh info/import/*.json from the markdown pack
uv run python -m scripts.import_tcet --wipe --fill-gaps   # seed Postgres (Phase 3: honest demand)
uv run python -m scripts.generate_college --instances 1 --clear-locks   # publish all (~2 min)
uv run python -m app.tests                         # 237 tests
cd frontend && npm run typecheck                   # NOT npm run build
```

Backend :8000, frontend :3001, admin@example.com / admin123. Postgres on host port **5433**.

> **Re-seed with `--fill-gaps`** — the importer now reports data gaps by default and only
> invents load (source=AUTOFILL, least-loaded qualified teacher) under `--fill-gaps`. The COMP
> seed uses it so every grid-taught subject has a teacher; PROJECT stays a reported gap.

## Gotchas (carried forward — still true)

- **alembic `env.py` uses `hide_password=False`** — do not revert; the masked URL broke migrations.
- **`npm run build` corrupts a running `next dev`** — use `npm run typecheck`. If dev hangs on
  "Checking session…": kill it, `rm -rf frontend/.next`, restart.
- **Backend dev server runs WITHOUT `--reload`** — restart manually after backend edits.
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
- **Capacity and faculty caps are OFF unless a profile row enables them** (DD-039) — tests that
  need them create a `hard_constraints` row first (see `t_faculty_cap`,
  `t_recurring_blackout`).
- **The feasibility report hard-fails oversubscribed runs with a 409** (DD-040) — an assignment
  asking for more sessions than the week can hold now fails before solving.
- **OR-Tools window co-location uses presence indicators** (DD-041) — the old per-pair equality
  was infeasible with 2+ room candidates and silently dropped every lab. `unplaced_count` now
  counts committed sessions, and the faculty caps honour the institutional toggle.
- `scripts/seed_demo.py` is a fabricated demo; `scripts/seed_tcet.py` is superseded by the importer.
