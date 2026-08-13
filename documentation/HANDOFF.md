# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, commit rules. Then the
sections below. This file is overwritten at the end of every session.

**Design decisions live in `documentation/design-decisions.md`** (permanent ADR log). The
OPEN items below are copied from it; resolve and mark done there.

---

## Session summary

State at handoff: **216/216 tests passing** (`uv run python -m app.tests`), frontend
typechecks (`npm run typecheck`). **The DB holds the real-data college scoped to the 6
branches with published grids (COMP/IT/EXTC/E&CS/MECH/CIVIL): 407 faculty (40 branch-bound
per branch, COMP = the real roster), 205 rooms (per-branch pools), 149 subjects, 540
assignments, 36 profiles — and a published, morning-filled timetable for all 36 classes
(~1,220 slots, 90 unplaced across the college, mostly classes legitimately near the 54-slot
weekly cap).** Generated from `info/import/*.json` + `info/import/synthetic_branches.json`
via `scripts/import_tcet.py`. Both servers running (backend :8000, frontend :3001);
admin@example.com / admin123.

### What changed this session

1. **Parallel per-batch practicals (DD-030)** — the founder's core complaint. A lab now
   expands into B sibling sessions placed atomically at the same (day, slot) in distinct
   rooms with distinct faculty:
   - `timetable_slots.batch_number` + `subject_assignments.batch_number` columns
     (migration `b3a1c7e2d9f4`).
   - Greedy solver: `_expand_lab_batches` / `_place_parallel_group` / `_parallel_rooms`;
     batch count auto-derived (FE → 3, SE+ → 2, `lab_batches` param override).
   - `MAX_ONE_LAB_PER_DAY` registry rule; group-double-book + same-subject-same-day skip
     parallel siblings (lab period = one division-wide session).
   - Exports show `Batch B{n}`; `SlotResponse` carries `batch_number`.
   - **Greedy-only** — OR-Tools keeps the whole-division model (documented in DD-030).
   - Tests: `app/tests/test_parallel_labs.py` (7 new).
2. **Real-data import pipeline** — `scripts/generate_tcet_import.py` (scraper session)
   emits `info/import/*.json`; the new `scripts/import_tcet.py` seeds Postgres from it
   (real departments incl. ES&H-owned FE, divisions from the published grids, real
   faculty/rooms/subjects with hours derived from the grids, per-division profiles with
   the real per-year grid + constraints, per-batch/per-period lab assignments). Unresolved
   faculty initials get **synthetic** members; any (group, subject) with no assignment is
   **auto-filled** so no subject silently vanishes. `scripts/seed_tcet.py` is superseded.
3. **Weekly lab periods** — `subject_assignments.period_number` (migration
   `c4d2e8f1a5b7`) separates a subject's parallel periods (CG: D1D2 Mon, D3D4 Wed); the
   solver places one atomic group per period. `ROOM_CAPACITY_SUFFICIENT` is batch-aware.
4. **Room affinity** — `preferred_rooms` profile param (a class's real venue/lab rooms)
   orders the room pool; generated classes reuse the college's rooms.
5. **Frontend** — TimetableGrid stacks parallel batches in one cell with `B{n}` badges and
   online labels; the generate page has a first-run "how a timetable is made" guide; the
   grid is wider/taller so stacked labs scroll instead of overlapping.
6. **Import-generator fixes** — the legend parser only matched `CODE = Name` and dropped
   every `CODE (INIT = Name)` legend; fixed to handle the real formats, plus grid slot
   times and a `period_id` per lab cell. Regeneration is deterministic.
7. **alembic/env.py bug fixed** — `render_as_string(hide_password=True)` put a literal
   `***` password in the migration URL. Now `hide_password=False`.
8. **Docs corrected** — `progress.md`/`plan.md`/`HANDOFF.md`/`timetable-generator-
   architecture.md` relabel the old seed a fabricated demo; new `timetable-audit.md`,
   `real-data-rollout-plan.md`, DD-030; `sample/esah_fe_department_info.md` and
   `sample/info-pack-discrepancies.md` (all 12 pack discrepancies resolved).
9. **Unplaced-sessions root causes fixed** (after a deepseek-pro strategist review):
   - **Branch-bound faculty pools** — teachers are branch-local; every branch gets ~40
     (COMP uses the real roster), via `scripts/build_synthetic_branches.py` →
     `info/import/synthetic_branches.json`. Profiles attach ONLY their own branch's
     faculty + rooms (no more college-wide shared pool that let one placeholder teacher
     burn his weekly cap across branches and starve the last one).
   - **Real scheme hours** replace the noisy grid cell-count derivation (lecture 3,
     tutorial 1, lab 2h, activity 2) — a class no longer requests 88 sessions for a
     54-slot week. Unplaced dropped 228 → 90; MECH-SE 53 → 6.
   - **Retire the class's own published timetable on republish** (router + generate_college)
     so a regeneration is not blocked by its own stale morning slots (the "everything in
     the evening" bug).
   - **Faculty caps** raised to 30h/wk, 8h/day.

### Honest state of the real-data rollout

Scoped to the 6 branches with published grids. COMP/IT are the honest demo (real faculty,
subjects, rooms, hours); EXTC is partial; E&CS/MECH/CIVIL are shape-only (the site
publishes no faculty for them — every teacher there is a synthetic placeholder, branch-
bound and renameable). All 36 classes publish morning-filled timetables with working
parallel labs; ~90 sessions unplaced college-wide (mostly COMP/IT SE classes legitimately
near the 54-slot weekly cap). Remaining gaps: ~59 ambiguous faculty initials, room
capacities/strengths, the branches with no published grids (AI&DS, IoT, CSE-IoT, CS&E,
MME, MBA/MCA/BCA), FE 2026-27, per-day grids + online/notional kinds.

---

## Next tasks (in order)

1. **DD-030 follow-ups** (see the DD-030 entry + `documentation/real-data-rollout-plan.md`):
   - per-day time grids (FE 08:00–18:30 with 15-min breaks + online Saturday IE/ISE),
   - online / no-room engine support (online subjects currently fall back to a
     classroom; `is_online` on slots/subjects + exports is the honest model),
   - resolve the ~59 unresolved faculty initials with the college (replace the synthetic
     placeholders),
   - tutorial/kind fidelity (split a subject's L/T/P streams onto distinct session kinds),
   - **placement report (strategist P3)** — surface the blocking constraint per unplaced
     session ("faculty at weekly cap", "no free room Mon 09:30") instead of just a count;
     the checker already returns reasons, thread them through the greedy solver.
   - **cell-for-cell verification** of a generated COMP-TE-D vs `info/import/timetables.json`.
2. **Frontend polish** — per-day grid rendering (FE), break rows per the real grid,
   onboarding on the other admin pages, and re-verifying the grid visually via the
   screenshot harness.
3. **College data** (unblocks E&CS/MECH/CIVIL fidelity): the faculty roster per branch,
   room capacities + floor map, class strengths, and the branches with no published grids.
4. **Docs sync** — keep `documentation/timetable-generator-architecture.md` §5 (engine:
   parallel practicals + preferred rooms) and §8 (params: `lab_batches`,
   `preferred_rooms`) in sync with the code.

## How to run

```bash
uv run alembic upgrade head                     # migrations b3a1c7e2d9f4 + c4d2e8f1a5b7
uv run python scripts/generate_tcet_import.py   # refresh info/import/*.json from the markdown pack
uv run python scripts/build_synthetic_branches.py  # regenerate per-branch faculty/room pools
uv run python -m scripts.import_tcet --wipe     # seed Postgres (real-data branches only)
uv run python -m scripts.generate_college --instances 1 --clear-locks  # publish all 36 (~2 min)
uv run python -m app.tests                      # 216 tests
cd frontend && npm run typecheck                # frontend types (NOT npm run build)
```

## Gotchas

- **alembic env.py now uses `hide_password=False`** — the password appears in the URL; do
  not revert (the old masked URL broke every migration).
- **`npm run build` corrupts a running `next dev`** — use `npm run typecheck`. If the dev
  server hangs on "Checking session…": kill it, `rm -rf frontend/.next`, restart.
- **The old `scripts/seed_demo.py` is a fabricated demo**, superseded by the importer.
  `scripts/seed_tcet.py` is a hand-built fallback; prefer the importer.
- **Backend dev server runs WITHOUT `--reload`** — restart it manually after backend edits.
- **Tests**: `uv run python -m app.tests` (not pytest). New test modules go in
  `app/tests/__main__.py`.
- **New `Settings` fields must go in `.env.example`** in the same commit.
- **Design decisions** go in `documentation/design-decisions.md` (DD-NNN), OPEN items are
  copied into this handoff; keep `timetable-generator-architecture.md` §3/§4/§5/§8 in sync.
