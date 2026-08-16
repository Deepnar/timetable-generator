# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, commit rules.

> ## ⚠️ START HERE: `documentation/system-audit-and-plan.md`
>
> An independent audit (15 Aug 2026) found the engine is **solving the wrong problem correctly**.
> That document is the current source of truth for what is wrong and what to build, in order.
> The decision record is **DD-031** in `documentation/design-decisions.md`.

---

## The one-paragraph situation

**Phase 5's core is DONE: fidelity scorer, synthetic problems, golden test, the tutorial-stream
fix (DD-046), and IT re-admission — 263 tests green, golden COMP+IT 21/21 divisions with zero
unplaced, pushed.** Phase 3b (constraint editing) and Phase 4's engine work are complete
(DD-042..045): tiers, facts document, positional cell parsing, pair merging, fail-fast/indexed
checking, most-constrained-first, quality-default, published-load caps. **Phase 5:** the A8
metrics are now a library (`app/engine/fidelity.py`, incl. grid-side-gap classification —
subjects whose cells name no teacher are the registrar's problem, not solver regressions);
`scripts/synthetic_problem.py` plants valid timetables and derives the solver inputs — four
shapes in the suite all solve with zero unplaced, including the D3 second-fixture shape (no
home rooms, 2-slot labs, break 3) with **zero engine changes** (no overfitting to TCET);
`scripts/golden_test.py` regenerates every division and fails on regression — **COMP+IT 21/21:
zero unplaced, zero break/Saturday violations, 100% room stability, 0 solver-attributable hour
misses (7 grid gaps)**. **DD-046:** IT's re-admission exposed the flattened-demand bug — the
grid's TUTORIAL cells inflated weekly_hours, every hour expanded as a LECTURE session, and
SAME_SUBJECT_SAME_DAY needed one distinct day per hour (IT-SE-C: 7h on 5 days → 4 unplaced).
`subject_assignments.tutorial_hours` (migration `d4e8f2a6c0b1`) splits the streams; IT-SE-C
4 → 0. Site publishes 21/21 divisions (COMP + IT).

**On "are the website timetables good now?"** — 21/21 divisions place every session with zero
rule violations; the fidelity scorer + golden test now make regressions visible numbers. The
remaining quality work is the frontend rendering (Phase 6 C1–C4), the deferred cohort/LNS
(DD-045), and the registrar-side data gaps (PROJECT mentors, unresolved initials).

---

## Work in order — each item says where to look and what "done" means

Full detail per phase is in `system-audit-and-plan.md` **Part E**. Findings are cross-referenced as
**[A*n*]** (engine), **[B*n*]** (bugs/security), **[C*n*]** (frontend), **[D*n*]** (generality).

> **Scope rule:** the importer defaults to `--codes COMP`; the live site runs `COMP,IT`. The
> remaining branches (EXTC, E&CS, MECH, CIVIL) are **shape-only synthetic** (fake teachers,
> `build_synthetic_branches.py`) — keep them OUT of golden scoring (the golden test's `--codes`
> flag makes that explicit) and re-admit only gated on the suite staying green.

### Phase 5 — remainder

1. **Second fixture through the importer adapter (D3, "CI generates both")** — the engine-level
   fixture test exists (synthetic problem, no home rooms, 2-slot labs); the adapter-level half
   needs a scratch Postgres (the importer's `--wipe` TRUNCATEs the live DB, so do NOT run it
   there). Build `scripts/build_fixture_other.py` writing `info/import-other/*.json` (6 slots,
   break 3, 5-day, 2 batches, 2-slot labs, no home rooms, full faculty names so the glossary
   path is not needed) + an `--import-dir` flag on `import_tcet.py`, then import → generate →
   score in a scratch DB.
2. **Remaining branches** — re-admit EXTC etc. one at a time (`--codes COMP,IT,EXTC` …), each
   gated on the golden test staying green; keep them out of the scored set while their data is
   synthetic (D4).
3. **Retire `build_synthetic_branches.py` as a scoring input** — done in practice (synthetic
   problems + golden replaced it); the script can stay for demo data but nothing scores on it.

### Phase 6 — Frontend (4–6 days) ← the big remaining chunk

**Confirmed on the live site (16 Aug 2026, COMP-SE-A/B instance pages):** the two visible
grid defects are exactly C2 + C3/C4, verified in code — the backend data is correct:

1. **Print stylesheet** — A4 landscape, one division per page. **[C1]**
2. **Redesign the parallel-batch cell** — `CellStack` (`TimetableGrid.tsx:194`) stacks 4 lab
   batches in a 76px row (`TimetableGrid.tsx:87`); text clips and batch badges overlap
   (COMP-SE-A Mon/Tue/Wed 08:30, Thu 14:30). A 2×2 split layout or auto-grown row height.
   DD-044 merged pairs record the representative batch on the slot — show the full pair from
   `window_key`/`batch_list`. **[C2]**
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
5. **Tutorial badges** — DD-046 sessions are TUTORIAL-typed now; the grid should render the
   tutorial stream distinctly.
6. Post-generation review: score breakdown, unplaced list **with reasons** (the checker already
   produces them and they are discarded), diff vs published. **[C6]**
7. Accessibility: grid semantics, keyboard nav, non-colour subject encoding; move route protection
   from `ProtectedShell` to middleware. **[C7]**

### Phase 4 — remainder (deferred by DD-045, build when needed)

1. **Per-group grid parameters** (`break_slots_by_group`, `working_days_by_group`,
   `saturday_policy_by_group`) through greedy scans, the checker's `NO_TEACHING_IN_BREAK_SLOT`,
   OR-Tools day domains, the importer, and the profile resolver.
2. **Cohort profiles** — one generation per (department, year); decide the artifact shape
   (cohort instance vs solve-once-slice-per-division) with the frontend.
3. **Construct-then-repair LNS** (A11) — greedy constructs; CP-SAT re-optimises small
   neighbourhoods. **Never post-filter a CP-SAT answer.**

### Phase 7 — Security hardening (2 days)

Central deny-by-default role table; role from the DB not the JWT (`utils/auth.py:100`); one DB
session per request (`main.py:150` + `:179` open two more); route-resolved auth exemption instead of
the `/auth/` string prefix (`main.py:141`); login rate limiting fails **closed**; startup assertions
on `SECRET_KEY` length and `CORS_ORIGINS != "*"`. **[B-MED-3 … B-LOW-6]**

---

## Open design decisions (from `design-decisions.md` — carry forward)

- **DD-046 follow-up** — the practical stream (a subject with LECTURE + LAB demand beyond the
  window model) may need the same two-stream treatment; today lab demand is window-shaped from
  the grid, which is the TCET pattern.
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
- **DD-037 follow-up** — PROJECT (BE-A/B/C) and online electives (IT-SE-A AAD etc.) have grid
  cells but no named teacher — the golden test classifies these as grid-side gaps; the college
  must supply the teachers.
- **DD-038 follow-up** — `preference_weight` on `faculty_subject_competency` is collected but not
  yet used by the least-loaded picker; a UI to manage competencies is a Phase 6 item.
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
- **DD-020 follow-up** — wire seed + battle test + golden test into CI or keep local; cadence after
  engine changes (the golden test is the natural CI gate).
- **DD-021 follow-up** — teacher/student read-scoping on list endpoints.
- **DD-022 follow-up** — WebSocket push + student "today" parity are polish.
- **DD-023 follow-up** — block-level overrides (moving one slot of a merged lab block leaves its
  siblings behind).
- **DD-024 (OPEN)** — the college's real rules; verify each against real data, then design. Superseded
  in priority by DD-031's phases (the tutorial stream, DD-046, resolves one of its items).

## Working agreements for this plan

- **Model before solver.** Do not optimise or replace a solver that is being asked the wrong
  question. Phases 1–2 changed the output shape; Phase 3 made the input honest; Phase 4 makes it
  complete.
- **Every phase ends with a measured number**, not a description. The metrics table above is the
  scoreboard; re-run `scripts/golden_test.py` and put the delta in the commit body.
- **No new synthetic people.** More fake teachers make bugs unattributable. See **[A9, D4]**.
- **No college constants in `app/engine/`.** They belong in the institution facts document. **[D2]**
- **Commits**: many small focused ones, impersonal voice, staged in logical chunks (`AGENTS.md`).
- **Docs in the same change**: `timetable-generator-architecture.md` §3 schema / §4 endpoints /
  §5 engine / §8 params, plus `plan.md` + `progress.md` checkboxes. New decisions → DD-047 onward in
  `design-decisions.md`.

## Reproducing every number in this handoff

```bash
# golden fidelity: regenerate every division, score, fail on regression
uv run python -m scripts.golden_test --codes COMP,IT

# synthetic problems: guaranteed-satisfiable instances, zero unplaced (in the suite)
uv run python -m app.tests

# weekly hours per (subject, division) vs the published grid (Phase 3 exit metric)
.venv/bin/python - <<'PY'
from app.database import SessionLocal
from app.engine.fidelity import hours_deltas, grid_gap_subjects
import json
db = SessionLocal()
tts = [t for t in json.load(open("info/import/timetables.json"))["timetables"]
       if t["group_name"].split("-")[0] in ("COMP", "IT")]
subjects = json.load(open("info/import/subjects.json"))["subjects"]
code_to_name = {(s["department_code"], s["semester"], s["code"]): s["name"] for s in subjects}
bad, total = hours_deltas(db, tts, code_to_name)
gaps = grid_gap_subjects(tts)
solver_bad = [b for b in bad if (b[0], b[1]) not in gaps and b[1] != "PROJECT"]
print(f"outside +-1: {len(bad)}/{total} (solver-attributable: {len(solver_bad)})")
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
uv run python -m scripts.import_tcet --wipe --fill-gaps --codes COMP,IT   # seed Postgres
uv run python -m scripts.generate_college --instances 1 --clear-locks   # publish all (21 profiles, ~2 min)
uv run python -m app.tests                         # 263 tests
uv run python -m scripts.golden_test --codes COMP,IT   # fidelity gate
cd frontend && npm run typecheck                   # NOT npm run build
```

Backend :8000, frontend :3001, admin@example.com / admin123. Postgres on host port **5433**.

> **Re-seed with `--fill-gaps`** — the importer re-seeds the college-default institutional
> constraint rows after `--wipe`, seeds the institution facts document (missing keys only), and
> reports data gaps by default. `parse_cell` lives in `scripts/cell_parser.py`; change the
> parser → regenerate (`generate_tcet_import.py`) → re-import → re-publish.

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
- **Tutorials are a second stream (DD-046)** — `subject_assignments.tutorial_hours` splits the
  weekly load; those sessions are TUTORIAL-typed and exempt from SAME_SUBJECT_SAME_DAY. The
  golden test classifies grid-side gaps (no teacher named) separately from solver regressions.
- **Institutional rules fire only from rows** (Phase 3b, DD-042) — tests rely on the college-
  default rows `seed_minimal` inserts (mirroring migration `c9d4e8f2a6b0`). Capacity and faculty
  caps stay off unless a `hard_constraints` row enables them (DD-039) — and count PUBLISHED load
  (A4).
- **`CollegeSettings.config_json` is the facts document** (DD-043) — `PUT /settings` MERGES
  key-by-key; the importer seeds `scheme_hours`/`year_strengths`/`batches_per_year` when missing.
- **The feasibility report hard-fails oversubscribed runs with a 409** (DD-040).
- **OR-Tools window co-location uses presence indicators** (DD-041); `unplaced_count` counts
  committed sessions; the faculty caps + SAME_SUBJECT_SAME_DAY parity honour the row gating.
- **`GET /constraints/types` shape changed in Phase 3b** — hard/soft are lists of
  `{type, tier, config_schema}` objects, not plain strings.
- **`is_valid` is fail-fast** (Phase 4 A6) — `check_all` still collects the full report.
- **Synthetic branches stay out of scoring** (D4) — `build_synthetic_branches.py` feeds the
  importer's branch pools but nothing scores on it; the golden test scores only the `--codes`
  you pass.
- `scripts/seed_demo.py` is a fabricated demo; `scripts/seed_tcet.py` is superseded by the importer.
