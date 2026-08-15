# Handoff — for the next session

Read `AGENTS.md` (repo root) first — commands, test entry points, commit rules.

> ## ⚠️ START HERE: `documentation/system-audit-and-plan.md`
>
> An independent audit (15 Aug 2026) found the engine is **solving the wrong problem correctly**.
> That document is the current source of truth for what is wrong and what to build, in order.
> The decision record is **DD-031** in `documentation/design-decisions.md`.
>
> **Do not start from `real-data-rollout-plan.md` or `timetable-audit.md`** — both are superseded
> for anything they claim about lab handling, hours derivation, or rollout health. The prior
> handoff described the real-data rollout as healthy; measured against the college's own published
> timetables, it is not.

---

## The one-paragraph situation

216/216 tests pass, all 36 divisions publish, and the output is structurally unlike a real
timetable. The engine's always-on hard constraints **reject the correct answer**: TCET's own
published timetables violate `SAME_SUBJECT_SAME_DAY` 160 times and `MAX_ONE_LAB_PER_DAY` 54 times,
and real labs are 1 slot where the engine forces 2. The real scheduling unit — a *lab window* where
one division splits into batches doing **different subjects** simultaneously — cannot be expressed
by the current model. This is a modelling error, not a solver weakness. Fix the model first.

**Current measured state** (36 published instances in the live DB):

| Metric | Now | Target |
|---|---|---|
| divisions with unplaced sessions | **26 of 36** | 0 |
| (division, subject) lecture pairs split across rooms | **245 of 245 (100%)** | <5% |
| sessions placed in the published BREAK row | **175** | 0 |
| Saturday sessions (COMP/IT/EXTC teach none) | **163** | 0 |
| lab pairs where some batch gets no practical | **35 of 63** | 0 |
| (subject, division) pairs with 2+ teachers | **37 of 245** | 0 |
| faculty utilisation | **5–32%**, 279 of 407 idle, 2 over cap | even |
| OR-Tools on real data | **half a timetable, zero practicals** | works or is not offered |

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
> | Entity | in DB | real | invented |
> |---|---|---|---|
> | rooms | 205 | 61 names (30%) | **144 (70%)** + **100% of capacities** |
> | faculty | 407 | 38 names (9%) | **369 (91%)** + **100% of workload caps** (30h/8h for all) |
> | student_groups | 36 | names | **100% of strengths** |
> | subjects | 149 | names + codes | **100% of hours_per_week** |
> | subject_assignments | 540 | subject↔group pairing | **100% of weekly_hours** |
>
> **The only fully real artefacts are `info/import/timetables.json` (46 grids, 2,451 cells) and
> `info/import/grids.json`.** Everything else is a real *name* with an invented *quantity*.
>
> Two consequences, both load-bearing:
> 1. **No constraint may depend on an INVENTED quantity.** `ROOM_CAPACITY_SUFFICIENT` compares an
>    invented 80 against an invented 70; the faculty caps enforce an invented 30h/8h. They are
>    shaping every placement using noise. Phase 3 item 7 turns them off until real data arrives.
> 2. **Score fidelity only against `timetables.json`.** Every A8 metric (room stability, batch
>    coverage, break-slot usage, Saturday, hours per subject) is derivable from it and depends on
>    **zero** invented quantities — which is exactly why nothing breaks when reality differs from
>    the placeholders.

### Phase 0 — Stop the bleeding (½ day) ← **start here**

1. **Security, critical.** `app/router/overrides.py:33` mounts at prefix `/instances` with **no role
   guard**, unlike `app/router/instances.py:23`. Any self-registered STUDENT can rewrite a published
   timetable via `POST /instances/{id}/overrides` or `.../slots/{id}/swap`. Add
   `dependencies=[Depends(require_roles("admin", "hod"))]`. Same for
   `app/router/notifications.py:44`. **[B-CRIT-1, B-HIGH-2]**
2. Add a regression test asserting **every** mutating route rejects a STUDENT token. This class of
   bug (per-file hand-added guards) has failed once already.
3. `app/engine/solvers/greedy_solver.py:776` references `Callable` without importing it — harmless
   today only because Python does not evaluate local annotations. Import it. **[B1]**
4. `app/engine/constraint_registry.py:768` — `CROSS_DEPT_DAILY_CAP` counts *all* of a faculty's
   sessions that day, not just cross-department ones. **[B2]**
5. DB unique constraint on `subject_assignments (subject_id, group_id, coalesce(batch_number,0),
   coalesce(period_number,0))` + a migration de-duplicating the existing 37 offending pairs. **[A3]**

**Done when:** a STUDENT token gets 403 on every mutating route; no class is taught the same subject
by two teachers.

### Phase 1 — Make the grid real (2–3 days)

Break is a **numbered slot** whose position varies per division (measured: slot 4×45, 5×51, 3×41,
6×28). `scripts/import_tcet.py:594` hardcodes `lunch_break_after_slot=4` and
`greedy_solver._build_slot_times` treats it as an *interval inserted after slot N* — so a 9-row grid
becomes 9 teachable slots plus an injected hour, ending 18:30 instead of 17:30.

1. Per-profile `break_slots: [int]` param, sourced per division from that division's BREAK cells in
   `info/import/timetables.json`. Delete the synthetic lunch arithmetic; read slot times verbatim
   from `grids.json`. **[A2]**
2. Per-division `working_days` + a `saturday_policy` param (`NONE|ACTIVITY_ONLY|FULL`). **[A2]**
3. New structural validator `NO_TEACHING_IN_BREAK_SLOT`.
4. `StudentGroup.home_room_id` (+ secondary) from the published `venue`, already parsed at
   `import_tcet.py:350`. **Hard-restrict** non-lab room domains to home rooms — a restriction, not a
   sort order. `preferred_rooms` only sorts, which is why room stability is 0%. **[A5]**
5. `ROOM_STABILITY` soft scorer.

**Done when:** 0 sessions in break slots, 0 Saturday sessions for COMP, room stability >95%, and
generated slot times match `grids.json` exactly.

### Phase 2 — Model the lab window (4–6 days) ← **the big one**

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

## Working agreements for this plan

- **Model before solver.** Do not optimise or replace a solver that is being asked the wrong
  question. Phases 1–2 change how the output looks; Phase 4 makes it complete.
- **Every phase ends with a measured number**, not a description. The metrics table above is the
  scoreboard; re-run it and put the delta in the commit body.
- **No new synthetic people.** More fake teachers make bugs unattributable. See **[A9, D4]**.
- **No college constants in `app/engine/`.** They belong in institution-profile parameters. **[D2]**
- **Commits**: many small focused ones, impersonal voice, staged in logical chunks (`AGENTS.md`).
- **Docs in the same change**: `timetable-generator-architecture.md` §3 schema / §4 endpoints /
  §5 engine / §8 params, plus `plan.md` + `progress.md` checkboxes. New decisions → DD-032 onward in
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
uv run python -m app.tests                         # 216 tests (plumbing only — see A8)
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
- `scripts/seed_demo.py` is a fabricated demo; `scripts/seed_tcet.py` is superseded by the importer.
