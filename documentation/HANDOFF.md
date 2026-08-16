# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, commit rules.

> ## ⚠️ START HERE: `documentation/system-audit-and-plan.md`
>
> An independent audit (15 Aug 2026) found the engine is **solving the wrong problem correctly**.
> That document is the current source of truth for what is wrong and what to build, in order.
> The decision record is **DD-031** in `documentation/design-decisions.md`.
>
> **Do not start from `real-data-rollout-plan.md` or `timetable-audit.md`** — both are superseded
> for anything they claim about lab handling, hours derivation, or rollout health.

---

## The one-paragraph situation

225 → **230 tests pass** (window suite added). The engine can now express the real scheduling
unit — a *lab window* where one division splits into batches doing **different subjects**
simultaneously (COMP-TE-D day 0: `Lab CG D1D2` + `Lab IIS D3D4`). Remaining structural gaps are
honest data/allocation problems (Phase 3), not modelling errors.

**Phase 0 (stop the bleeding) is DONE**: role guards on every mutating route (B-CRIT-1/B-HIGH-2),
`subject_assignments` dedup + unique index (A3), `Callable` import (B1), `CROSS_DEPT_DAILY_CAP`
counting fix (B2). Recorded as **DD-032/DD-033**.

**Phase 1 (make the grid real) is DONE**: `break_slots` + verbatim `slot_times`, `saturday_policy`,
`NO_TEACHING_IN_BREAK_SLOT`, home-room hard restriction, `ROOM_STABILITY` scorer. Recorded as
**DD-034/DD-035**. Measured on the 11 COMP divisions: **0 break-slot sessions, 0 Saturday sessions,
100% room stability, slot times exactly match `grids.json`**.

**Phase 2 (model the lab window) is DONE**: group-scoped `period_number`, window construction,
`_is_parallel_sibling` by `window_key`, `MAX_ONE_LAB_PER_DAY` counts windows, `LAB_ROTATION_COMPLETE`
Latin-square validator, `SAME_SUBJECT_SAME_DAY` relaxed to lectures-only, OR-Tools window support.
Recorded as **DD-036**. **Measured: 21/30 windows fully co-located (up from 0), 21 carry 2+
subjects; COMP-TE-D day 0 is the real shape.**

**Current measured state** (live DB is now **COMP-only, 11 published instances** — re-seeded under
the Phase 0–5 scope rule `REAL_DATA_CODES = {"COMP"}`):

| Metric | Phase 0 (audit, 36 divs) | Phase 2 (11 COMP divs) | Target |
|---|---|---|---|
| sessions in a break slot | 175 | **0** | 0 |
| Saturday sessions | 163 | **0** | 0 |
| lecture pairs split across rooms | 245 of 245 | **0 of 100% in-venue** | <5% |
| lab windows co-located (all batches same day+slot) | 0 (unexpressible) | **21 of 30 (70%)** | 100% |
| lab windows carrying 2+ subjects | 0 (unexpressible) | **21 of 30 (70%)** | ~67% (audit's 52/78) |
| divisions with unplaced sessions | 26 of 36 | still present | 0 (Phase 4) |
| lab pairs where some batch gets no practical | 35 of 63 | **0** (COMP had none) | 0 |
| (subject, division) pairs with 2+ teachers | 37 → 0 (deduped) | **0** | 0 |
| faculty utilisation | 5–32%, 279 idle, 2 over cap | COMP-only (~54 fac) | even (Phase 3) |
| OR-Tools on real data | half a timetable, zero practicals | fixed (windows + batch_number) | works or not offered |

> **Note:** unplaced sessions persist but are now *honest* — Phases 1–2 removed the fake Saturday,
> break-slot, and per-subject-lab capacity that was hiding them. Zero-unplaced is Phase 4's job.
> The 9 scattered windows are all shared-faculty data gaps (unresolved initials — Phase 3).

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
> Live DB is now **COMP-only** (Phase 0–5 scope rule). Counts for the 6-branch seed (for
> reference) were: 205 rooms (61 real names), 407 faculty (38 real), 36 groups, 149 subjects,
> 540→495 assignments. Current COMP seed: **41 rooms, 390 faculty (~59 synthetic for unresolved
> initials), 11 groups, 30 subjects, 200 assignments**.
>
> | Entity | in DB (COMP) | real | invented |
> |---|---|---|---|
> | rooms | 41 | COMP venue + cell names | **100% of capacities** |
> | faculty | 390 | real roster names | synthetic names + **100% of workload caps** (30h/8h) |
> | student_groups | 11 | names + venue | **100% of strengths** |
> | subjects | 30 | names + codes | **100% of hours_per_week** |
> | subject_assignments | 200 | subject↔group pairing | **100% of weekly_hours** |
>
> **The only fully real artefacts are `info/import/timetables.json` (46 grids, 2,451 cells) and
> `info/import/grids.json`.** Everything else is a real *name* with an invented *quantity*.
>
> Two consequences, both load-bearing:
> 1. **No constraint may depend on an INVENTED quantity.** Phase 3 item 7 turns three of them off.
>    **Measured: this changes nothing today** — `ROOM_CAPACITY_SUFFICIENT` and both faculty caps
>    reject **0 of 31,370** candidate evaluations. They are inert *because* the numbers are
>    invented, and become load-bearing the moment real data arrives (capacity) or cohort solving
>    lands (caps). Zero-risk to remove now; must be switched on deliberately later.
> 2. **Score fidelity only against `timetables.json`.** Every A8 metric (room stability, batch
>    coverage, break-slot usage, Saturday, hours per subject) is derivable from it and depends on
>    **zero** invented quantities — which is exactly why nothing breaks when reality differs from
>    the placeholders.
>
> **Full ledger, the counterfactual measurements, the data we must eventually collect (ranked), and
> the per-branch coverage table: `documentation/data-requirements.md`.**
>
> Headline from that doc: **`MAX_ONE_LAB_PER_DAY` alone causes 64% of unplaced sessions** (22 → 8
> across 5 divisions when removed) — one line at `import_tcet.py:615`, enforcing a rule the real
> timetable violates 54 times. Phase 2 is the correct fix; this is the size of the prize.

### Phase 0 — Stop the bleeding ✅ DONE (15 Aug 2026)

All five items shipped, tested, committed in four focused commits, pushed:

1. `require_roles("admin","hod")` on `overrides.py` (B-CRIT-1); `notifications.py` gated to all
   four roles — it is recipient-scoped self-service, so admin/hod-only would have broken the
   portal bell (B-HIGH-2; **DD-033**).
2. Mutation-sweep regression test in `test_security.py` — enumerates every mutating route in the
   OpenAPI schema, asserts a STUDENT token is 403 except the public auth + recipient-scoped
   notification paths. A new unguarded router fails the suite the same day.
3. `Callable` imported in `greedy_solver.py` (B1).
4. `CROSS_DEPT_DAILY_CAP` counts only cross-dept sessions (B2; recomputed from subject/group
   departments since `TimetableSlot` doesn't persist the flag).
5. Unique expression index `(subject_id, group_id, COALESCE(batch_number,0),
   COALESCE(period_number,0))` + dedup migration `e6a1b7c3d9f2` (540 → 495 rows); `POST/PUT
   /assignments` return 409 on duplicates (A3). **DD-032** records that `load_share` shared-teaching
   is incompatible with the constraint and untouched.

**Open from DD-032:** shared teaching (two teachers, one subject, `load_share` 0.8/0.2) is
currently impossible under the unique index. The solver ignores `load_share` today, so nothing
breaks; if it is ever wanted it needs its own mechanism, not duplicate rows.

### Phase 1 — Make the grid real ✅ DONE (15 Aug 2026)

Five items shipped, tested, committed in six focused commits, pushed:

1. `break_slots: [int]` per profile (modal BREAK slot from the division's published grid) +
   `slot_times` read verbatim from `grids.json`; the synthetic lunch arithmetic is now only the
   fallback for grid-less colleges. **[A2]**
2. Per-division `working_days` (from days that actually teach) + `saturday_policy`
   (`NONE|ACTIVITY_ONLY|FULL`). **[A2]**
3. `NO_TEACHING_IN_BREAK_SLOT` structural validator (breaks a block that spans a break too). **[A2]**
4. `StudentGroup.home_room_id` + `home_room_secondary_id` (migration `f7b2c8d4e1a3`); `_get_rooms`
   hard-restricts non-lab sessions to the venue. **[A5]**
5. `ROOM_STABILITY` soft scorer, stamped on imported profiles.

**Exit metrics measured (11 COMP divisions):** 0 break-slot sessions · 0 Saturday sessions ·
100% room stability · slot times exactly match `grids.json` (0 mismatches) · day ends 17:30.

**Open from DD-034:** the real grids sometimes move the break by day (COMP-SE-A: slot 4 Mon-Wed,
slot 5 Thu-Fri). The single `break_slots: [int]` picks the modal slot; per-(day, slot) break data
is a future refinement.

### Phase 2 — Model the lab window ✅ DONE (16 Aug 2026)

Seven items shipped, tested, committed in six focused commits, pushed:

1. `period_number` re-scoped to the GROUP (window = (group, period); members =
   (batch, subject, faculty)); importer groups lab cells by (day, slot-run). **[A1]**
2. Window construction: `_build_sessions` groups by `(group, period)`, `_expand_lab_batches`
   emits one session per batch with its own subject. **[A1]**
3. `_is_parallel_sibling` matches `window_key`, not subject. **[A1]**
4. `MAX_ONE_LAB_PER_DAY` counts windows per group per day. **[A1]**
5. `LAB_ROTATION_COMPLETE` (Latin square, constructed from the grid, never searched). **[A1]**
6. `SAME_SUBJECT_SAME_DAY` relaxed to lectures-only default, labs/tutorials exempt. **[A1]**
7. OR-Tools calls `_expand_lab_batches`, models window co-location, propagates
   `batch_number`/`window_key`. **[A6]**

**Exit metrics measured (11 COMP divisions):** 21/30 windows fully co-located (up from 0), 21
carry 2+ subjects, COMP-TE-D day 0 = CG batches 1,2 + IIS batches 3,4 at the same slot.

**Open from DD-036:** the 9 scattered windows are shared-faculty data gaps (unresolved initials
like HP vs HPK, SPS) — a Phase 3 data-collection item, not a model bug. The rotation is read from
the grid's declared members, not re-derived by the solver.

### Phase 3 — Honest demand and honest allocation ← **start here**

Ground truth, `COMP-TE-D` day 0 slot 5: `Lab CG D1D2 SuS/PD 324` **and** `Lab IIS D3D4 SPS/PM 325`
— one window, two subjects, four teachers. `COMP-BE-A` shows the rotation explicitly:
`period 1: DWM→batches 1,2 | CSS→batches 3,4`; `period 2: the swap`.

1. Re-scope `period_number` from *(subject, group)* to **group**. A window is
   `(group_id, period_number)`; members are `(batch_number, subject_id, faculty_id)`.
2. `ParallelWindow` scheduling unit; `_expand_lab_batches` (`greedy_solver.py:471`) builds windows,
   not per-subject groups. Fix the grouping at `greedy_solver.py:299`.
3. `_is_parallel_sibling` (`constraint_registry.py:527`) matches **window identity**, not subject.
4. `MAX_ONE_LAB_PER_DAY` counts **windows** per group per day.
5. Construct the batch↔subject rotation as a **Latin square** before solving (window `k` gives batch
   `i` subject `(i+k) mod K`); add `LAB_ROTATION_COMPLETE` validation. Don't search for it.
6. Relax `SAME_SUBJECT_SAME_DAY` from always-on to configurable, defaulting to "at most one
   *lecture* per subject per day; labs and tutorials exempt" — which is exactly what the 160 real
   violations are. **[A1]**
7. Fix `ORToolsSolver` to expand windows and propagate `batch_number`.

**Done when:** batch coverage is 100%, lab windows carry multiple subjects, and a generated
`COMP-TE-D` is recognisably the same *shape* as `info/import/timetables.json`.

### Phase 3 — Honest demand and honest allocation (3 days)

`scripts/import_tcet.py:160` computes `_derive_hours()` from the published grids **and never reads
it**; `_scheme_hours()` gives every lecture a flat 3h instead. Then auto-fill (line 496) invents
assignments with a modulo teacher rotation — which is why 279 teachers are idle while two are over
cap.

1. Use `_derive_hours()`; `_scheme_hours()` becomes the logged fallback. **[A3]**
2. Demote auto-fill to an explicit `--fill-gaps` step that **reports** data gaps instead of
   inventing load.
3. Replace the modulo rotation (`import_tcet.py:539`) with least-loaded assignment. **[A9]**
4. New `faculty_subject_competency` table; assignment and `_lab_batch_faculty` may only pick
   qualified teachers. **[A9, B4]**
5. Prune `profile_resources` (currently 3,710 rows) to teachers who actually hold an assignment.
6. `source` provenance (`GRID|SCHEME|AUTOFILL`) on `subject_assignments`, surfaced in the UI. **[C5]**
7. Pre-solve feasibility report (demand vs capacity per resource).

**Done when:** weekly hours per (subject, division) within ±1 of the published grid; nobody over cap
while anyone qualified is idle.

### Phase 3b — Make constraints editable (2 days)

**Eight registered validators are not in the `ConstraintType` enum**, so they are unreachable through
the API and only insertable by direct DB write — including `SAME_SUBJECT_SAME_DAY` and
`MAX_ONE_LAB_PER_DAY`, the two that contradict reality most.

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
6. Fix OR-Tools' `unplaced_count` under-report (`or_tools_solver.py:239` counts from `chosen`, before
   the safety-net filter deletes placements). **[B9]**
7. **Construct-then-repair with LNS** — greedy constructs; CP-SAT re-optimises small neighbourhoods
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

1. **Print stylesheet** — A4 landscape, one division per page. A timetable's primary output is paper.
   `TimetableGrid` has a `min-w-[980px]` scroll container and no print CSS. **[C1]**
2. Redesign the parallel-batch cell — `CellStack` (`TimetableGrid.tsx:194`) hides the 3rd/4th batch
   behind a scrollbar in a 76px row. After Phase 2, windows routinely hold 4. **[C2]**
3. `breakAfterSlot` → `breakSlots: number[]`; make `slotTime` required (its default invents a 30-min
   grid). **[C3, C4]**
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
  window cannot co-locate (distinct-faculty rule). Fix in Phase 3 via faculty resolution /
  `faculty_subject_competency`, not in the solver.
- **DD-034 follow-up** — the real grids sometimes move the break by day (COMP-SE-A: slot 4
  Mon-Wed, slot 5 Thu-Fri); the single `break_slots: [int]` picks the modal slot. A per-(day,
  slot) break model would need per-day break data; worth revisiting in Phase 2 when lab windows
  change how a day is structured anyway.
- **DD-032 follow-up** — shared teaching (two teachers, one subject) is blocked by the new unique
  index; the solver ignores `load_share` so nothing breaks today. If wanted later, needs its own
  mechanism (a per-session teacher share), not duplicate rows.
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
  question. Phases 1–2 change how the output looks; Phase 4 makes it complete.
- **Every phase ends with a measured number**, not a description. The metrics table above is the
  scoreboard; re-run it and put the delta in the commit body.
- **No new synthetic people.** More fake teachers make bugs unattributable. See **[A9, D4]**.
- **No college constants in `app/engine/`.** They belong in institution-profile parameters. **[D2]**
- **Commits**: many small focused ones, impersonal voice, staged in logical chunks (`AGENTS.md`).
- **Docs in the same change**: `timetable-generator-architecture.md` §3 schema / §4 endpoints /
  §5 engine / §8 params, plus `plan.md` + `progress.md` checkboxes. New decisions → DD-037 onward in
  `design-decisions.md`.

## Reproducing every number in this handoff

```bash
# engine rules vs the real published timetables (160 / 54 / 131-of-133)
# current output quality (unplaced, room churn, Saturday, break-slot usage)
# faculty utilisation and idle count
# greedy vs OR-Tools benchmark
# -> all four scripts are in system-audit-and-plan.md, Appendix
```

## How to run

```bash
uv run alembic upgrade head
uv run python scripts/generate_tcet_import.py      # refresh info/import/*.json from the markdown pack
uv run python scripts/build_synthetic_branches.py  # per-branch pools (being retired — see D4)
uv run python -m scripts.import_tcet --wipe        # seed Postgres
uv run python -m scripts.generate_college --instances 1 --clear-locks   # publish all (~2 min)
uv run python -m app.tests                         # 230 tests (plumbing only — see A8)
cd frontend && npm run typecheck                   # NOT npm run build
```

Backend :8000, frontend :3001, admin@example.com / admin123. Postgres on host port **5433**.

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
- `scripts/seed_demo.py` is a fabricated demo; `scripts/seed_tcet.py` is superseded by the importer.
