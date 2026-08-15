# Independent System Audit & Rebuild Plan

**Date:** 2026-08-15
**Method:** read the code that actually executes; ignore prior notes/AI summaries; verify every
claim against the live Postgres DB (36 real generation runs) and the 46 scraped TCET timetables in
`info/import/timetables.json`.
**Scope:** the whole generation pipeline, then backend security, then frontend/UX.

---

## 0. Verdict in one paragraph

The engine is not broken. It is **solving the wrong problem correctly**. TCET's real timetable is
built from a scheduling unit the engine cannot represent — a *lab window* in which one division
splits into batches that simultaneously do **different subjects** in different labs with different
teachers, rotating week to week. The engine models "one subject, N batches". On top of that, three
of the always-on / auto-stamped hard rules **forbid patterns that appear in the real published
timetable**, the time grid is off by one hour and one column, and the demand fed to the solver is
fabricated rather than derived. The search algorithm is the *least* important cause. Fixing the
data model and the constraint set will do more than any solver upgrade.

The proof, computed from the college's own published timetables:

| Engine rule | Status | Times the **real TCET timetable** violates it |
|---|---|---|
| `SAME_SUBJECT_SAME_DAY` | always-on structural, cannot be disabled | **160** of 611 (division, day, subject) groups |
| `MAX_ONE_LAB_PER_DAY` | stamped onto all 36 profiles by the importer | **54** of 192 (division, day) pairs |
| lab = 2 contiguous slots (`CONTIGUOUS_LAB_SLOTS default_block_length=2`) | stamped onto all 36 profiles | real labs are **1 slot in 131 of 133** cases |

An engine whose hard constraints reject the correct answer cannot produce the correct answer.

---

## Part A — The generation pipeline

### A0. Empirical baseline (what the system produces today)

From the 36 published instances currently in the DB:

- **26 of 36 divisions dropped sessions.** Warnings range from 1 to 7 unplaced sessions
  (`IT-SE-A`: 7, `IT-SE-D`: 7, `COMP-SE-A`: 6, `MECH-SE/TE/BE`: 6 each).
- **245 of 245 (division, subject) lecture pairs are split across multiple rooms.** That is
  100%. `COMP-SE-D` uses **29 distinct rooms** for 50 cells. Computer Graphics is taught to
  `COMP-TE-D` in rooms 512, COMP-CR-15, 336, 607, 608 and 718 — six rooms for one subject.
  The real division has one venue: `718/608/610`.
- **163 sessions placed on Saturday.** Real COMP/IT/EXTC divisions teach zero Saturday classes.
- **175 sessions placed in slot 4**, which is the published **BREAK** row.
- **35 of 63 (division, lab subject) pairs leave at least one batch with no practical at all.**
  Observed batch coverage sets: `(1,2,3,4)`×28, `(1,2)`×16, `(1,2,3)`×10, `(1,3)`×3, `(3,)`×3,
  `(3,4)`×2, `(1,)`×1.
- **The same subject is taught to the same class by two different teachers**, alternating by day
  (see `COMP-TE-D` Computer Graphics: Neha Wankhede / Nikhil Joshi on alternate days).
  37 of 245 non-batch (subject, group) pairs have more than one assignment row.

Student idle-gap rate is only 2.3%, so *compactness is not the problem*. The problem is that the
output is structurally unlike a real timetable.

---

### A1. ROOT CAUSE #1 — the "lab window" is not modelled (highest impact)

**What the real data says.** `info/import/timetables.json`, `COMP-TE-D`, day 0 slot 5:

```
Lab CG  D1D2 SuS/PD 324     <- batches 1,2 -> subject CG,  room 324, teachers SuS+PD
Lab IIS D3D4 SPS/PM 325     <- batches 3,4 -> subject IIS, room 325, teachers SPS+PM
```

One time window, one division, **two different subjects**, two labs, four teachers. Across the
`COMP-BE-A` windows the rotation is explicit:

```
period 1:  DWM -> batches 1,2   |   CSS -> batches 3,4
period 2:  CSS -> batches 1,2   |   DWM -> batches 3,4
```

Measured across all 46 real timetables: **52 of 78 lab windows carry two or more distinct lab
subjects**; only 26 carry one. The dominant pattern is the one the engine cannot express.
Windows carry 3 distinct subjects 17 times and 4 subjects 10 times.

**What the code does.** `app/engine/solvers/greedy_solver.py:299` groups assignment rows by
`(subject_id, group_id)` **first**, then by `period_number` inside that. So `period_number` is
scoped to a subject, not to the division. Consequences, in order:

1. `_expand_lab_batches` (`greedy_solver.py:471`) builds one parallel group per *(subject, period)*.
   Two different lab subjects can never be co-located in one window — nothing links them.
2. `_is_parallel_sibling` (`constraint_registry.py:527`) requires
   `committed_slot.subject_id == candidate.subject_id`. Different subjects in the same window are
   therefore treated as a **group double-book** and rejected.
3. `MAX_ONE_LAB_PER_DAY` — which `scripts/import_tcet.py:615` stamps on **every** profile — then
   forbids two lab subjects on the same day at all, pushing each lab subject onto its own day.
4. Because there is no window-level batch bookkeeping, batches are covered ad hoc. The engine
   produced `COMP-TE-D` CG-Lab for batch 1+2 on Mon, batch 4 *alone* on Tue, batch 3 *alone* on
   Wed. During Tue s6–s7 the whole division is marked busy while **three quarters of the class has
   nothing to do**, because `NO_GROUP_DOUBLE_BOOK` blocks the group for the batch that is in the lab.

**The fix (design).** Promote the lab window to a first-class scheduling unit.

- Re-scope `period_number` from *(subject, group)* to **group**. A window is
  `(group_id, period_number)`; its members are `(batch_number, subject_id, faculty_id)` rows.
- Introduce `ParallelWindow` alongside `SessionToSchedule`: one atomic placement that occupies one
  (day, slot-range) and consumes one room per member.
- `_is_parallel_sibling` matches on **window identity** (same group, same day, overlapping slots,
  same window id), *not* on subject.
- `MAX_ONE_LAB_PER_DAY` counts **windows** per group per day, not lab sessions.
- Add a `LAB_ROTATION_COMPLETE` validator: over the set of windows, every batch must receive every
  lab subject exactly once. This is a Latin square and should be **constructed**, not searched:
  with `B` batches and `K` lab subjects, window `k` assigns batch `i` to subject `(i + k) mod K`.
  Construct it in the session-expansion phase and hand the solver a pre-formed rotation to place.

This one change fixes the batch-coverage holes, removes the artificial lab-day explosion, and makes
the generated grid recognisably TCET-shaped.

---

### A2. ROOT CAUSE #2 — the time grid is wrong by one hour and one column

**Break is a real slot, and its position differs per division.** In the published grids the break
occupies a numbered row. Measured across the 46 real timetables, the BREAK row sits at slot
**4 (45×), 5 (51×), 3 (41×), 6 (28×), 2 (15×), 8 (3×), 7 (2×)** — staggered, as it must be for a
college that cannot seat everyone at once.

**What the code does.** `scripts/import_tcet.py:594-599` hardcodes
`lunch_break_after_slot = 4` for every 9-slot grid, and `greedy_solver._build_slot_times`
(`greedy_solver.py:146`) treats the break as an *interval inserted after slot N* rather than a slot.
So for a 9-row published grid running 08:30–17:30 the engine generates:

- **9 teachable slots** where the college has 8 teachable + 1 break;
- an extra 60 minutes injected after slot 4, so the day ends at **18:30, not 17:30**;
- every slot from 5 onward has a wall-clock time that does not match the published grid;
- 175 sessions currently sit in the break row.

**Saturday.** The grids carry `working_days: [0,1,2,3,4,5]` and the importer passes that straight
through (`import_tcet.py:600`), but the grid's own `saturday` field says
`"IP / co-curricular / notional learning"`. Only 11 of 46 real divisions (mostly MBA/BCA/FE) have
any Saturday teaching; COMP/IT/EXTC have none. The engine placed 163 Saturday sessions.

**The fix.**
- Replace `lunch_break_after_slot` / `lunch_break_duration_minutes` with a per-profile
  `break_slots: [int]` JSON param — the slot numbers that are non-teaching for *that division*,
  read from the BREAK cells of that division's published timetable.
- Build slot times **directly from the grid rows** (`grids.json` already carries exact
  `start`/`end` per slot). Delete the synthetic time arithmetic entirely; it can only drift.
- Derive `working_days` per division from the days that actually carry teaching cells, and add a
  `saturday_policy` param (`NONE` / `ACTIVITY_ONLY` / `FULL`).
- Add a structural `NO_TEACHING_IN_BREAK_SLOT` validator so this can never regress.

---

### A3. ROOT CAUSE #3 — the demand handed to the solver is fabricated

**`_derive_hours()` is computed and then thrown away.** `scripts/import_tcet.py:160` calls it and
binds `subject_hours, group_hours` — **neither is ever read again**. What is used instead is
`_scheme_hours()` (`import_tcet.py:85`), a flat constant: `LECTURE→3, LAB→2, TUTORIAL→1,
ACTIVITY→2`. Every lecture subject in the college is asked for exactly 3 hours a week regardless of
what the college actually does.

Compare demand to reality:

| | engine demand | real published load |
|---|---|---|
| COMP sem 3 | 8 subjects × 3h = **24 lecture-hours** | `COMP-SE-A`: 14 LECT + 4 TUT + 8 LAB = 26 teaching cells *total* |
| EXTC sem 5 | 9 subjects × 3h = **27 lecture-hours** | `EXTC-SE-A`: 21 LECT + 2 TUT + 0 LAB = 23 cells total |
| MECH sem 4 | 8 subjects × 3h = **24 lecture-hours** | `MECH-TE`: 24 LECT total, 0 labs |

Then **auto-fill makes it worse.** `import_tcet.py:496-545` walks every subject in `(dept, sem)`
and, if the class has no assignment for it, invents one with a rotating arbitrary teacher
(`dept_fac[(g.id + subj_idx) % len(dept_fac)]`). It does not check whether a *real* row already
exists under a different subject-kind key, which is how 37 (subject, group) pairs ended up with 2–4
assignment rows — hence "Kinematics of Machinery, 12 h/week, four different teachers" for `MECH-SE`.

The source JSON is 100% null on every quantity that matters: `subjects.hours_per_week` 231/231 null,
`assignments.weekly_hours` 432/432 null, `groups.strength` 46/46 null, `rooms.capacity` 84/84 null,
`faculty.name` 88/126 null. Also `subjects.kind` is `LECTURE` for all 231 rows and
`subjects.room_type` is `CLASSROOM` for all 231 — there is not a single LAB subject in the source;
they are all synthesised later at `import_tcet.py:394`.

**The fix.**
- **Use `_derive_hours()`.** It already computes per-division weekly load from the published grid
  cells, which is ground truth. Fall back to `_scheme_hours()` only where the grid is silent, and
  log every fallback.
- **Delete auto-fill, or demote it.** Make it a separate, explicit, reported step
  (`--fill-gaps`) that reports "class X has no teacher for subject Y" as a *data gap for the
  registrar to resolve*, rather than silently inventing load. A timetable system that invents
  teachers is not trustworthy.
- **Deduplicate assignments.** Add a DB unique constraint on
  `(subject_id, group_id, coalesce(batch_number,0), coalesce(period_number,0))`. One class, one
  subject, one teacher, one row.
- Record data provenance per row (`source: GRID | SCHEME | AUTOFILL`) and surface it in the UI, so
  a generated timetable can honestly say which parts rest on real data.

---

### A4. ROOT CAUSE #4 — one division at a time, published-sequentially

All 36 profiles are `scope_type = DIVISION` with exactly one group each. The whole college is built
by generating division 1 → publishing it → generating division 2 → … Cross-division safety comes
**only** from `Scheduler._load_published_conflicts()` (`scheduler.py:441`), which reserves
`(id, day, slot)` triples per resource.

Two consequences:

1. **Load caps are not shared across runs.** `FACULTY_MAX_HOURS_PER_DAY` and
   `FACULTY_MAX_HOURS_PER_WEEK` (`constraint_registry.py:645, 664`) count only `committed` — this
   instance's slots. `MAX_CONSECUTIVE_SAME_TEACHER`, `MAX_DAILY_SUBJECTS` and `CROSS_DEPT_DAILY_CAP`
   have the same blindness. A teacher who teaches four divisions has their weekly cap checked four
   times against a quarter of their real load. The caps are effectively inert.
2. **Order determines quality.** Division 1 takes the best rooms and slots; division 28 gets
   whatever survives. This is exactly the gradient visible in the run log — the later, larger COMP
   and IT divisions are the ones with 5–7 unplaced sessions.

**The fix.** Solve a **cohort** in one run.

- Target: one generation per `(department, year)` — all 4 COMP-SE divisions together — or per
  department. `ScopeType` already supports `DEPARTMENT`; the profile machinery already supports
  multiple groups. The greedy expansion already filters by `profile_group_ids`
  (`greedy_solver.py:265`), so multi-group is mostly a data-shape change, not a rewrite.
- Bridge (ship this first, it is cheap): extend `_load_published_conflicts()` to also return
  per-faculty `{faculty_id: {day: count, week: count}}` from published instances, and seed the
  checker's counters with it so caps are honest across runs.
- Add a **cohort-level pre-check** that reports infeasibility *before* solving: total demanded
  hours vs. available (group-slots, room-slots per type, faculty-hours). Today a 7-session shortfall
  only shows up as a warning string on a COMPLETED run.

---

### A5. ROOT CAUSE #5 — no concept of a home room

A real division owns a classroom (`COMP-TE-D` → `718/608/610`) and leaves it only for practicals.
The engine has no such concept. `preferred_rooms` (`greedy_solver.py:645`) only *sorts* the room
list; the moment the top room is taken by another division's published timetable, the solver
silently walks down the list. With 36 divisions publishing sequentially into a shared room pool,
every division ends up scattered. Result: **245/245** lecture pairs split across rooms.

**The fix.**
- Add `StudentGroup.home_room_id` (and `home_room_secondary_id`), populated from the published
  timetable's `venue` field, which the importer already parses at `import_tcet.py:350`.
- For non-lab sessions, restrict the room domain to the home rooms — a hard restriction, not a sort
  order. Falling back to the general pool should require an explicit profile flag and should raise a
  warning, because in the real world it means the registrar has over-allocated the room.
- Reserve home rooms up front: a division's home room is blocked for other divisions for the whole
  week. That is how the college actually allocates.
- Add a `ROOM_STABILITY` soft scorer (fraction of a division's lectures in its home room) so the
  metric is visible and regressions are caught.

---

### A6. ROOT CAUSE #6 — the search is one-shot greedy with no repair, and quality is opt-in

`GreedySolver.solve()` (`greedy_solver.py:852`) places sessions in a single forward pass. A session
that finds no valid slot is appended to `unscheduled` and **dropped** — there is no backtracking, no
ejection, no repair. `unplaced_count` is the only trace.

Additional problems in the surrounding orchestration:

- **"Most constrained first" barely orders anything.** `greedy_solver.py:330` sorts on two booleans
  (is-lab, is-cross-dept). It ignores room scarcity, faculty scarcity, weekly hours and group load —
  the factors that actually decide feasibility.
- **The diversity loop discards better solutions.** `scheduler.py:268-313`: unless
  `variation == BEST`, the scheduler takes the **first attempt that differs** from previously
  accepted ones, regardless of quality. Soft scoring is computed but not used to choose. Quality is
  therefore opt-in twice over (`variation=BEST` **and**
  `settings.enable_soft_constraint_scoring`), and the default path optimises nothing.
- **Seeding barely diversifies.** `solve()` shuffles `slot_times`, but every scan function
  (`_group_balance_scan`, `_preference_scan`, `_criterion_scan`) re-sorts by slot number, and
  `sorted()` is stable with a unique key — so the slot shuffle has **zero effect**. Only the day
  order and room order actually vary.
- **`enable_soft_constraint_scoring` gates the greedy preference scan.** `greedy_solver.py:770`
  returns `None` when the flag is off, so soft rules do not influence placement at all in the
  default configuration.
- **OR-Tools silently loses lab batches.** `ORToolsSolver.solve()` overrides `solve()` and never
  calls `_expand_lab_batches`. With batched real data, `_build_sessions` yields one base session per
  period carrying `parallel_batch_map`, and CP-SAT places only *that* session with
  `period_rows[0]`'s faculty. Every other batch's teacher and room is dropped, and no
  `batch_number` is written to `TimetableSlot`. **The premium solver is unusable on the real data.**
- **CP-SAT gets a 5-second default budget** (`or_tools_solver.py:43`) and `randomize_search=True`
  when seeded — both work against solution quality.

**The fix.**
- Short-circuit validation: `ConstraintChecker.is_valid` calls `check_all`, which runs all 14
  structural rules and collects every violation even after the first failure
  (`constraint_checker.py:112-131`). Add a fail-fast path that returns on the first violation.
  This is the single cheapest large speedup in the codebase.
- Index committed slots. Every structural validator does a linear scan over `committed`
  (`constraint_registry.py:475-524` etc.). Replace with dicts keyed by `(faculty, day, slot)`,
  `(room, day, slot)`, `(group, day, slot)`. The current cost is roughly
  *sessions × days × slots × rooms × committed*, re-run 6× per instance by the diversity loop.
- Add a **repair phase**: after the forward pass, run min-conflicts / ejection-chain over the
  unplaced set (evict a blocking session, place the failed one, re-place the evicted one). This is
  what turns 26-divisions-with-holes into zero.
- Make quality the default: always score, always keep the best distinct attempt, and stop gating the
  preference scan behind a feature flag.
- Fix OR-Tools: call `_expand_lab_batches`, model windows, propagate `batch_number`, raise the
  default time budget, drop `randomize_search`.

---

### A7. Correctness bugs found (independent of the above)

| # | Location | Issue |
|---|---|---|
| B1 | `greedy_solver.py:776` | `Callable` is referenced in an annotation but **never imported**. It does not raise today only because PEP 526 does not evaluate local variable annotations. Any refactor that lifts it to module/class scope turns it into a `NameError`, and it fails type-checking now. |
| B2 | `constraint_registry.py:768` | `CROSS_DEPT_DAILY_CAP` counts **all** of a faculty's sessions that day, not just cross-department ones. With `max_cross_dept_per_day: 2`, a teacher with two normal sessions is blocked from any cross-dept work. |
| B3 | `greedy_solver.py:267` | `block_lengths = self._lab_block_lengths()` is dead — recomputed per assignment at line 384. Each call re-scans every hard constraint. |
| B4 | `greedy_solver.py:441` `_lab_batch_faculty` | When no batched rows exist it fills remaining batches from the profile faculty pool by lowest id — assigning **teachers who do not teach that subject**. Produces plausible-looking but fabricated staffing. |
| B5 | `scheduler.py:335` | `placement_warning` reports only the **final** instance's unplaced count; earlier instances' shortfalls are invisible. |
| B6 | `scheduler.py:267` | Type annotation declares a 3-tuple; a 4-tuple is appended at line 288. |
| B7 | `profile_resolver.py:242` | `_cast_param` calls `int()`/`float()`/`json.loads()` with no guard — one malformed parameter row becomes an uncaught 500. |
| B8 | `constraint_registry.py:454` | `_availability_window_applies` returns `False` when `slot_date is None`, so all date-bounded faculty unavailability is silently inert unless the profile sets `term_start`. Correct but a silent trap; it should warn. |

---

### A8. The tests measure mechanics, not timetable quality

`uv run python -m app.tests` → **216/216 passed**, while the production output is what Section A0
describes. Every test runs against `seed_minimal()` toy data and asserts on plumbing: "a 2h lab
block expands into per-batch sessions", "greedy places both batches in distinct rooms". Nothing
asserts that a generated timetable is *good*.

**The fix — golden-fidelity tests.** The 46 real TCET timetables are a labelled dataset. Build a
scorer and assert on it in CI:

| Metric | Target | Today |
|---|---|---|
| unplaced sessions | 0 | 26/36 divisions have some |
| lecture room stability (one venue per division) | ≥ 95% | 0% |
| batch coverage (every batch does every lab subject) | 100% | 44% |
| sessions in a break slot | 0 | 175 |
| Saturday sessions where policy is NONE | 0 | 163 |
| weekly hours per (subject, division) vs. published | within ±1 | up to 4× |
| teachers per (subject, division) | 1 | up to 4 |

Then add a **regression corpus**: generate all 36 divisions, score them, fail CI if any metric
degrades. This turns "the timetables aren't that good" from a feeling into a number.

---

### A9. The data is NOT the bottleneck — allocation is

The obvious instinct is "I need more teachers / more branches / better scraped data." **Measured
against the live DB, that is wrong.** Supply vastly exceeds demand:

| Branch | divisions | demanded h/wk | teachers | capacity h/wk | **utilisation** |
|---|---|---|---|---|---|
| Computer Engineering | 11 | 511 | 54 | 1620 | **32%** |
| Information Technology | 10 | 475 | 72 | 2160 | **22%** |
| Electronics & Telecom | 6 | 129 | 52 | 1560 | **8%** |
| Mechanical | 3 | 102 | 48 | 1440 | **7%** |
| Electronics & CS | 3 | 81 | 45 | 1350 | **6%** |
| Civil | 3 | 72 | 48 | 1440 | **5%** |

And the distribution is pathological:

- **279 of 407 teachers have ZERO assignments.** 128 carry the entire college.
- Meanwhile the busiest are **over their cap**: Dr. Sunita Pachori 33h and Ms. Pratiksha Deshmukh
  33h against a 30h limit; Ms. Neha Wankhede exactly at 30h. The cap is being violated because
  per-run caps do not compose across divisions (see A4).
- Rooms: **145 classrooms for 36 divisions** and **60 labs** against a peak of 4 simultaneous
  batches per window. Both are 4× oversupplied.

**So the scarcity that starves the solver is entirely manufactured**, by:
1. auto-fill's modulo rotation `dept_fac[(g.id + subj_idx) % len(dept_fac)]` (`import_tcet.py:539`),
   which keeps landing on the same handful of people while 279 sit idle;
2. the real COMP roster names absorbing all genuine assignments;
3. caps not being enforced across divisions, so the concentration is never pushed back on.

**Adding more synthetic teachers would make things worse**, not better. Every idle teacher is
attached to every profile in that branch (`profile_resources` is already **3,710 rows**), which
inflates the solver's search space and slows every run without adding a single placeable hour.

**What to do with the data instead — in priority order:**

1. **Fix allocation, not volume.** Replace the modulo rotation with a real load-balancing
   assignment: sort candidate teachers by current committed load and pick the least-loaded one that
   can teach the subject. This alone moves utilisation from "2 people over cap, 279 idle" to an even
   spread, and removes most unplaced sessions without touching the solver.
2. **Add a `qualified_subjects` relation.** Right now *any* department teacher can be assigned *any*
   department subject (`import_tcet.py:508`). That is why B4 (`_lab_batch_faculty`) can hand a
   practical to someone who has never taught it. A `faculty_subject_competency` table (faculty ×
   subject, optionally with a preference weight) is the single highest-value **new** data structure,
   and it is small enough to collect from the college by hand.
3. **Prune, don't grow.** Attach to a profile only the teachers who actually have an assignment for
   that division's subjects. Expect `profile_resources` to fall from 3,710 to a few hundred.
4. **Then collect real data, in this order of payoff:**
   - **class strengths + room capacities** (46 + 84 nulls) — unblocks `ROOM_CAPACITY_SUFFICIENT`,
     which is currently comparing invented 63/70 strengths against invented 80/60 capacities;
   - **the ~59 unresolved faculty initials** — turns synthetic placeholders into real people;
   - **per-subject L/T/P scheme hours** from the syllabus PDFs in `sample/` — these are published
     documents and would replace the derived-hours guess entirely;
   - the branches with no published grids (AI&DS, IoT, CSE-IoT, CS&E, MME, MBA/MCA/BCA) — lowest
     priority, because they add breadth to a system that is not yet correct on the 6 branches it has.

**Rule of thumb going forward:** every synthetic row must be *labelled* as synthetic (see the
`source` provenance column in Phase 3) and must be *excluded* from fidelity scoring. Otherwise the
system grades itself against its own inventions.

---

### A10. Constraints: hardcoded vs editable — the split is in the wrong place

You asked whether constraints are internal or editable from outside. **Both — and the boundary is
drawn exactly backwards.** There are three layers:

**Layer 1 — Structural rules (hardcoded, always-on, cannot be disabled by anyone).**
`STRUCTURAL_RULES` (`constraint_registry.py:43`) is a 14-entry tuple dispatched on every candidate
regardless of any DB row. `ConstraintChecker._check_configured` (`constraint_checker.py:148`)
explicitly **skips** any DB row of a structural type — the comment says such a row "stays
decorative". So creating a `SAME_SUBJECT_SAME_DAY` row with `is_active = false` does nothing; the
rule still fires.

**Layer 2 — Data-driven registry rules (editable via `POST /constraints/hard`).**
Type + `config_json`, validated against the `ConstraintType` enum by Pydantic.

**Layer 3 — College feature flags** (`CollegeSettings`: `enable_lab_batches`,
`allow_cross_dept_subjects`, `enable_soft_constraint_scoring`, `config_json.max_cross_dept_per_day`).

**The problem — measured, not asserted.** Eight registered validators are **not in the
`ConstraintType` enum at all**, so `HardConstraintCreate` rejects them and they can only be inserted
by direct DB write:

```
CROSS_DEPT_DAILY_CAP                  FACULTY_MAX_HOURS_PER_DAY
FACULTY_MAX_HOURS_PER_WEEK            MAX_ONE_LAB_PER_DAY
NO_CROSS_TIMETABLE_GROUP_CONFLICT     NO_CROSS_TIMETABLE_ROOM_CONFLICT
NO_CROSS_TIMETABLE_TEACHER_CONFLICT   SAME_SUBJECT_SAME_DAY
```

Read that list against Part A. **The rules that most need to be tunable per college are precisely
the ones that are unreachable.** `SAME_SUBJECT_SAME_DAY` — which the real timetable breaks 160 times
— is always-on *and* not expressible. `MAX_ONE_LAB_PER_DAY` — which the real timetable breaks 54
times — is only insertable by `import_tcet.py` writing the ORM object directly, and cannot be edited
or removed through the API afterwards.

**The fix — a three-tier policy model:**

| Tier | Meaning | Examples | Editable? |
|---|---|---|---|
| **INVARIANT** | Physics. A person/room cannot be in two places at once. | `NO_TEACHER_DOUBLE_BOOK`, `NO_ROOM_DOUBLE_BOOK`, `NO_GROUP_DOUBLE_BOOK`, cross-timetable conflicts | Never |
| **INSTITUTIONAL** | Real policy that varies by college and *must* be tunable | `SAME_SUBJECT_SAME_DAY`, `MAX_ONE_LAB_PER_DAY`, faculty caps, `ROOM_CAPACITY_SUFFICIENT`, break/Saturday policy | **Yes — enum + API + UI** |
| **PREFERENCE** | Soft, weighted, never blocks | the six soft rules | Yes |

Concretely:
1. Split `STRUCTURAL_RULES` into `INVARIANT_RULES` and a new `DEFAULT_INSTITUTIONAL_RULES`.
2. Institutional rules run **only** when a profile (or the college default set) carries a row —
   with a migration that seeds today's behaviour so nothing changes silently.
3. Add every registered validator to the `ConstraintType` enum. Add a startup assertion that
   `set(HARD_CONSTRAINT_REGISTRY) == set(ConstraintType hard members)` so the two can never drift
   again — this drift is what produced the eight-rule gap.
4. Expose `GET /constraints/types` with tier + JSON-schema for each `config_json`, and build a
   constraint editor in the UI. A registrar must be able to say "we allow two labs a day" without a
   code change. **That is the actual product.**

---

### A11. The solver question: is there something better than OR-Tools?

You said you don't know whether the Google one ever works. **It does not — on your data.** Measured
directly, greedy vs CP-SAT on three real profiles:

| Profile | solver | slots | lab slots | unplaced | batches placed | time |
|---|---|---|---|---|---|---|
| COMP-TE-D | greedy | 46 | 22 | 1 | 1,2,3,4 | 398 ms |
| COMP-TE-D | **OR-Tools** | **24** | **0** | 6 | **none** | 2742 ms |
| COMP-SE-A | greedy | 47 | 20 | 6 | 1,2,3,4 | 565 ms |
| COMP-SE-A | **OR-Tools** | **27** | **0** | 8 | **none** | 2237 ms |
| IT-SE-A | greedy | 46 | 22 | 7 | 1,2,3,4 | 468 ms |
| IT-SE-A | **OR-Tools** | **24** | **0** | 9 | **none** | 2322 ms |

CP-SAT produces **half a timetable with zero practicals**, is worse than greedy on every metric, and
takes 5× longer. Three compounding causes:

1. `ORToolsSolver.solve()` never calls `_expand_lab_batches`, so batched labs collapse to a single
   whole-division session (A6).
2. CP-SAT does not model `MAX_ONE_LAB_PER_DAY`, so it packs lab subjects onto the same day — which
   is *correct* real-world behaviour — and then the final safety-net checker
   (`or_tools_solver.py:227`) silently deletes every one of them.
3. **New bug (B9):** `unplaced_count = len(sessions) - len(placed_sessions)` (`or_tools_solver.py:239`)
   is computed from `chosen`, **before** the safety-net filter. Placements the filter discards are
   still counted as placed, so the reported unplaced figure is far too low. The 6/8/9 above are
   understatements.

**Is CP-SAT the wrong tool?** No. CP-SAT is the correct engine for this problem — it is what serious
timetabling systems converge on. What is wrong is the integration: a "prune the domain, then filter
the answer" architecture, where any rule CP-SAT cannot express becomes a post-hoc deletion. That
design can only ever lose sessions.

**Recommended architecture — construct, then repair (do not pick one solver):**

1. **Construct** with the greedy pass. It is fast (~0.5 s), already handles windows and batches, and
   is guaranteed feasible-or-explicit.
2. **Repair with CP-SAT under Large Neighbourhood Search.** Freeze the timetable, unfreeze a
   neighbourhood (one day, or one division, or the sessions blocking an unplaced item), and let
   CP-SAT re-optimise just that window against the *full* objective. Iterate until no unplaced
   sessions remain or the budget expires. Windows are small, so CP-SAT solves them to optimality in
   milliseconds — which is exactly where it is strongest, and it sidesteps the whole-model blowup
   that currently forces a 5-second timeout.
3. **Never post-filter.** Every rule must be either modelled in CP-SAT or enforced during
   construction. If a rule cannot be modelled, it must reject a *neighbourhood*, not silently delete
   a placement.

Alternatives considered and why not:
- **Pure metaheuristic (simulated annealing / tabu).** Genuinely good at the "make it pretty"
  objectives, and worth adding later as a polish pass. But it needs a complete feasible start —
  which is the construct phase — so it does not replace step 1, and it gives weaker guarantees than
  CP-SAT on hard constraints.
- **Pure CP-SAT over the whole college.** Elegant, and the right long-term target once cohort
  solving (Phase 4) lands. Premature now: with the current model it would just find the wrong answer
  faster.

**Bottom line: fix the model first.** With windows, home rooms and the correct grid in place, greedy
alone will already produce timetables that look right. LNS repair then removes the last unplaced
sessions and tightens quality. Rewriting the solver before fixing the model would be wasted work.

---

## Part B — Backend security

### B-CRIT-1 — Privilege escalation: any student can rewrite published timetables

`app/router/overrides.py:33` mounts at prefix `/instances` with **no role dependency**:

```python
router = APIRouter(prefix="/instances", tags=["Mid-year changes"])   # <- no guard
```

Compare `app/router/instances.py:23`, which correctly carries
`dependencies=[Depends(require_roles("admin", "hod"))]`.

The global `require_auth` middleware (`app/main.py:138`) only checks *that a token is valid*, never
the role. Self-registration is public and creates a `STUDENT` (`auth.py:56`). So the full chain is:

1. `POST /auth/register` — public, no auth, creates a STUDENT account.
2. `POST /auth/login` — get a bearer token.
3. `POST /instances/{id}/overrides` — **mutates a published timetable slot**.
4. `POST /instances/{id}/slots/{a}/swap` — swaps two published slots.
5. `DELETE /instances/{id}/overrides/{id}` — removes an override.

**Fix:** add `dependencies=[Depends(require_roles("admin", "hod"))]` to the overrides router.
**Then fix the class of bug:** the pattern "router-level guard, added by hand, per file" already
failed once. Invert it — make the middleware deny by default and require every router to declare
its allowed roles in one central table, so a new unguarded router fails closed.

### B-HIGH-2 — `notifications.py` is unguarded

`app/router/notifications.py:44` also has no role dependency. Verify that
`GET /notifications/` scopes to the calling admin and is not a cross-tenant read.

### B-MED-3 — Role is trusted from the JWT, never re-checked

`require_roles` (`utils/auth.py:100`) reads `role` from the token payload with **no DB lookup**.
`authenticate_token` re-validates `is_active` against the DB but not `role`. Demoting a user has no
effect until their token expires (default 60 min). Read the role from the `Admin` row that
`authenticate_token` already loaded, and attach it to `request.state`.

### B-MED-4 — Two DB sessions per authenticated request

`require_auth` (`main.py:150`) opens a `SessionLocal()`, and `_write_audit` (`main.py:179`) opens
another for every mutating request — on top of the route's own `get_db`. Under load this triples
pool pressure. Resolve the admin once in the middleware and stash it on `request.state`; make the
audit write async or batched.

### B-MED-5 — Path-prefix auth exemption

`main.py:141` exempts anything starting with `/auth/`. `request.url.path` is not normalised by
uvicorn, so `/auth/../rooms` skips the auth middleware. It currently 404s because the router will
not match the un-normalised path, so this is not exploitable today — but it is one proxy
configuration away from being so. Match on the resolved route, not a string prefix.

### B-LOW-6 — Other items

- `CORS_ORIGINS` with `allow_credentials=True` — add a startup assertion that it is never `*`.
- Rate limiting is Redis-backed and **fails open** (`auth.py:29`: "Returns None (allow) when Redis
  is unavailable"). For login, fail closed or fall back to an in-process limiter.
- No account lockout after repeated failures; 5/min/IP is trivially distributed.
- `POST /reset` is admin-guarded but should require a typed confirmation phrase and write an audit
  entry before, not after, execution.
- JWT in `localStorage` (`frontend/src/lib/api.ts:26`) is XSS-readable. Prefer an httpOnly cookie
  with CSRF protection, or accept the risk explicitly and document it.
- `config.py` has no `SECRET_KEY` default (good — it is required) but no length/entropy check; add
  a startup assertion of ≥32 bytes and refuse to boot in `ENV=production` with a weak key.

---

## Part C — Frontend & UX

The stack (Next 14 App Router, TanStack Query + Table, Radix, Tailwind) is a sound choice and the
component layer is tidy. The gaps are about *the timetable being a document*, not about React.

### C1 — The grid does not print
A college timetable's primary output is paper on a noticeboard and a PDF in a WhatsApp group.
`TimetableGrid` (`frontend/src/features/timetable/TimetableGrid.tsx`) has a `min-w-[980px]` scroll
container and no print stylesheet. **Add `@media print`**: fixed A4 landscape, one division per
page, no scroll container, no chrome, black-on-white with a legend. This is the single highest-value
frontend change.

### C2 — Parallel batches are hidden behind a scrollbar
`CellStack` (line 194) sets `overflow-y-auto` once three or more batches share a window. Inside a
76px row, the 3rd and 4th batch are invisible. Once A1 lands, a window will routinely hold 4
(batch, subject, room, teacher) entries. Redesign the cell as a **split window**: one bordered block
per batch laid out horizontally with the batch number as a leading chip, expanding the row height
for lab rows rather than clipping.

### C3 — The break is rendered from the wrong model
`breakAfterSlot` (line 53) mirrors the backend's "insert a row after slot N" idea. Once A2 lands,
change the prop to `breakSlots: number[]` and render those slot rows as break rows in place.

### C4 — Default slot times are invented
`slotTime` defaults to `8 + Math.floor((s-1)/2)` (line 64) — a 30-minute grid. The real grid is
60-minute from 08:30. Any caller that forgets to pass `slotTime` shows wrong times on a timetable.
Make it a required prop.

### C5 — Trust and provenance
Given A3, the UI must be honest about what is real. Add a per-cell provenance affordance
(published grid / derived / auto-filled) and a generation summary banner: *"38 of 41 sessions
placed. 3 unplaced: MP Lab batch 4, …"*. Today `placement_warning` is a bare string and the run
still reads COMPLETED.

### C6 — The generate flow has no feedback loop
`app/generate/page.tsx` is 228 lines of form. What is missing is the **review** step: after a run,
show the score breakdown per soft rule, the unplaced list with *why* each failed (the checker
already produces human-readable reasons — they are discarded), and a side-by-side against the
previous published version. `instances/compare` exists; wire it into the generate flow.

### C7 — Accessibility & mechanics
- The grid is a `div` grid with no `role="table"`/`columnheader`/`rowheader` semantics and no
  keyboard cell navigation (arrow keys). Cells are `<button>`s, so they are at least focusable.
- Colour is the only carrier of subject identity (`chartColor(subjectId)`) — add a text/pattern
  fallback and verify contrast in both themes.
- Route protection is client-side only (`ProtectedShell`), so protected pages flash before
  redirect. Move the gate to middleware.
- No optimistic updates or offline handling in `SlotEditor` — a failed override silently reverts.

---

## Part D — Generality: are we modelling TCET, or marrying it?

> *"if we make things for the data, or make data for the thing, this system won't ever work on a
> malleable env right — if anything changes it might break ALL."*

This is the right worry, and it needs a sharp distinction, because the answer is different for
different parts of the plan.

### D1 — Vocabulary vs. answers

There are two ways to encode a college into a system:

- **Encoding its *answers*** — "lunch is after slot 4", "labs are 2 hours", "COMP/IT/EXTC/E&CS/
  MECH/CIVIL", "SE strength is 63". This is what breaks when the college changes anything.
- **Encoding its *vocabulary*** — "a break is a slot, and which slot is per-division data",
  "a lab window binds N batches to one time", "a division has a home room". This is what lets the
  college change freely.

**Everything in Phases 1–2 is vocabulary, not answers.** None of it is TCET-specific:

| Concept | TCET-specific? | Reality |
|---|---|---|
| Lab window with batch↔subject rotation | **No** | Universal in Indian engineering colleges; standard worldwide wherever practicals split a cohort |
| Break as a numbered slot, position varying per division | **No** | Any institution too large to seat everyone at once staggers lunch |
| A division has a home room it mostly stays in | **No** | Near-universal below university level |
| Saturday policy as a per-cohort setting | **No** | Varies by college, year, and programme |
| Weekly hours derived from a published scheme | **No** | Every accredited programme publishes an L/T/P scheme |

The engine today cannot express *any* of these. That is not "too general" — it is **too poor to
model a real college at all**. Right now the system can only produce timetables for an imaginary
institution where every subject meets 3×/week, nobody eats lunch, classes teleport between 29 rooms,
and a lab never runs two subjects at once. Fixing this makes the engine *more* general, not less.

**The overfitting risk is real, but it lives somewhere else** — in `scripts/import_tcet.py`, which
hardcodes TCET's answers into the engine's supply chain:
`REAL_DATA_CODES = {"COMP", "IT", ...}` (line 45), `lunch_break_after_slot = 4` (line 596),
`default_block_length = 2` (line 613), `{1: 63, 2: 63, 3: 70, 4: 60}` strengths (line 371),
`_scheme_hours` constants (line 85), `batches = 3 if g.year == 1 else 2` (line 527).

### D2 — The boundary to enforce

Draw one hard line and never cross it:

```
  ENGINE                    |  INSTITUTION PROFILE          |  SOURCE ADAPTER
  (generic, no college      |  (declarative data: this      |  (per-source, throwaway)
   names, no constants)     |   college's answers)          |
  --------------------------+-------------------------------+---------------------------
  lab windows, rotation     |  break_slots: [4]             |  scripts/import_tcet.py
  break slots, home rooms   |  batches_per_division: 4      |  (TCET website scrape)
  batch/session expansion   |  saturday_policy: NONE        |
  constraint registry       |  lab_block_slots: 1           |  scripts/import_<other>.py
  solvers                   |  scheme_hours: {L:3,T:1,P:2}  |  CSV / manual entry / API
```

**The engine must contain zero college-specific constants.** Everything currently hardcoded in
`import_tcet.py` becomes fields on an *institution profile* — a declarative document the college
owns and can edit through the UI. The importer's only job is to produce that document from one
source; a different college writes a different adapter, or fills the form by hand, and the engine
never changes.

You already have most of this machinery: `TimetableProfile` + `profile_parameters` +
`hard_constraints` is exactly the right shape. The problem is that the interesting knobs
(`break_slots`, batch count, lab block length, Saturday policy) either don't exist as parameters or
are unreachable through the API (see A10). **Phase 1–2 mostly consists of turning hardcoded
constants into profile parameters** — which is the anti-overfitting work, not the overfitting work.

### D3 — The test that proves you haven't overfitted

Assertion, not intention: **add a second fixture college with a deliberately different shape**, and
make CI generate for both.

```
fixtures/tcet.json      9 slots, break varies 3–6, 6-day week, 4 batches, 1-slot labs, home rooms
fixtures/other.json     6 slots, break at slot 3,  5-day week, 2 batches, 2-slot labs, no home room,
                        no Saturday, morning-only faculty, 40-min slots
```

If adding `fixtures/other.json` requires touching anything under `app/engine/`, you have overfitted
— fix it then, not six months later. This one test is worth more than any amount of care, because it
converts "we should stay general" from a good intention into a build failure.

### D4 — Synthetic data: generate *problems*, not *people*

The current synthetic approach (`build_synthetic_branches.py`) invents 240 plausible teacher names.
Per A9 that actively hurts: 279 of them have no assignments, they bloat every profile, and — worst —
**they make bugs indistinguishable from data gaps.** When MECH-SE drops 6 sessions you cannot tell
whether the solver failed or the fake roster was incoherent.

Do the opposite. Generate **problem instances with a known-good answer**:

1. Pick a shape (divisions, subjects, batches, slots, rooms, teachers).
2. **Construct a valid timetable first** — place sessions into slots respecting every invariant.
   This is easy, because you are not searching; you are laying down a pattern.
3. **Derive the inputs from it**: weekly hours = how many times each subject was placed; teacher
   assignments = who you placed; room pool = what you used; rotation = the pattern you laid.
4. Hand the derived inputs to the solver.

This gives you three things nothing else does:
- **A guaranteed-satisfiable instance.** Any unplaced session is now provably a solver bug, not data
  ambiguity. Today you cannot make that claim about a single one of the 90 unplaced sessions.
- **A known optimum to score against**, so "is this timetable good?" gets a number.
- **Unlimited scale and shape variation** — 5 divisions or 200, 2 batches or 6 — for free.

Keep the human-plausible names only for demos and screenshots. Never let them into scoring.

### D5 — So: COMP first, or all six branches?

**COMP first. Narrow and real beats broad and fake.**

- COMP is the only branch with a genuine roster (~39 published names), real grids for SE/TE/BE, and
  **11 divisions** — enough to exercise every hard case at once: parallel labs with rotation, shared
  faculty across 11 divisions, cross-year room contention, and the SE/TE/BE grid differences.
  If the engine is right for COMP, it is right.
- The other five branches are shape-only. E&CS/MECH/CIVIL have **no published faculty at all** —
  every teacher is a placeholder. They contribute no signal and actively conceal bugs, because a bad
  result there is unattributable.
- They are also the direct cause of the 279 idle teachers distorting every capacity number in A9.

**Concretely:** scope the working set to COMP (11 divisions, ~54 teachers, real subjects and rooms).
Get every fidelity metric in A8 green there. *Then* re-admit IT (which has partial real data), then
the rest. Breadth is a data-collection problem for the college to solve; it is not engineering work,
and it should not gate engineering work.

### D6 — Data provenance ledger: what is actually real

You cannot reason about fidelity without knowing which fields are observed and which are invented.
Measured against the live DB:

| Entity | in DB | real | invented | which fields are invented |
|---|---|---|---|---|
| **rooms** | 205 | 61 names (30%) | **144 (70%)** | **100% of capacities** (80 classroom / 60 lab / 45 synth-lab defaults). `room_type` is not in the source either — it is *derived* from whether a room hosts a LAB cell. |
| **faculty** | 407 | 38 names (9%) | **369 (91%)** | **100% of `max_hours_per_week` / `max_hours_per_day`** (30/8 for everyone) |
| **student_groups** | 36 | names real | — | **100% of strengths** (`{1:63, 2:63, 3:70, 4:60}`) |
| **subjects** | 149 | names + codes real | — | **100% of `hours_per_week`** (flat 3/2/1 from `_scheme_hours`) |
| **subject_assignments** | 540 | subject↔group pairing real | — | **100% of `weekly_hours`**; teacher identity real only where an initial resolved |

**The only fully real artefacts are `info/import/timetables.json` (46 published grids, 2,451 cells)
and `info/import/grids.json` (slot times + working days).** Everything else is a real *name* with an
invented *quantity* attached.

**The consequence, and it is a big one: a constraint driven by an invented quantity is worse than no
constraint at all.** It restricts the search using noise, and its effect is indistinguishable from a
real rule. Two are live right now:

- `ROOM_CAPACITY_SUFFICIENT` compares an **invented capacity (80)** against an **invented strength
  (70)**. It is pure fabrication on both sides, and it is currently shaping every placement.
- `FACULTY_MAX_HOURS_PER_DAY` / `_PER_WEEK` enforce an **invented 8/30** for all 407 teachers.
  Section A9 shows two teachers already sitting at 33h against that invented 30 — so the cap is
  simultaneously fabricated *and* not enforced.

**Rule to adopt: no constraint may depend on a field whose provenance is `INVENTED`.** Until the
college supplies real capacities, strengths and workloads, those three rules default **off** — under
the INSTITUTIONAL tier from A10, so switching them on is a UI toggle the day the data arrives. This
is also what protects you from the exact failure you are worried about: if reality differs from the
invented number, nothing breaks, because nothing was ever relying on it.

**What this means for testing.** Score fidelity **only** against `timetables.json` — the real
output of a real scheduling process. Shape metrics (room stability, batch coverage, break-slot
usage, Saturday, hours per subject) are all derivable from it and depend on **zero** invented
quantities. That is why the A8 metric table deliberately contains no capacity or workload metric.

### D7 — What actually protects you when the college changes its mind

Three things, in order:

1. **The fidelity suite (Phase 5).** If "no session in a break slot" and "one venue per division"
   are CI assertions, a change that breaks them fails the build the same day. Today nothing would
   catch any of the 6 regressions in A0.
2. **The second fixture college (D3).** Stops TCET assumptions from re-entering the engine.
3. **Institutional constraints being editable (A10).** If the registrar can change "max labs per
   day" from 1 to 2 in the UI, a policy change is a Tuesday afternoon, not a release.

Note what is *not* on that list: getting the data perfect. You will never have perfect data, and the
college will keep changing. Design for that instead of trying to outrun it.

---

## Part E — The plan

Ordered by *impact per unit of work*. Phases 0–2 are the ones that change how the output looks.

> **Scope rule for Phases 0–5: COMP only** (11 divisions, real roster, real grids — see D5).
> Set `REAL_DATA_CODES = {"COMP"}` in `import_tcet.py` and re-seed. Re-admit IT at Phase 5, the
> rest after. Do not let breadth gate correctness.

### Phase 0 — Stop the bleeding (½ day)
1. Add `require_roles("admin","hod")` to `overrides.py` and `notifications.py`. **[B-CRIT-1, B-HIGH-2]**
2. Add a regression test asserting every mutating route rejects a STUDENT token.
3. Import `Callable` in `greedy_solver.py`; fix `CROSS_DEPT_DAILY_CAP` counting. **[B1, B2]**
4. Add the DB unique constraint on `subject_assignments`; write a migration that de-duplicates the
   existing 37 offending pairs. **[A3]**

*Exit:* no privilege escalation; no class taught the same subject by two teachers.

### Phase 1 — Make the grid real (2–3 days)
1. `break_slots: [int]` per profile, sourced per division from the published BREAK cells; delete the
   synthetic lunch arithmetic; build slot times from `grids.json` rows verbatim. **[A2]**
2. Per-division `working_days` + `saturday_policy`. **[A2]**
3. `NO_TEACHING_IN_BREAK_SLOT` structural validator.
4. `StudentGroup.home_room_id` from the published `venue`; hard-restrict non-lab room domains to
   home rooms; reserve home rooms college-wide. **[A5]**
5. `ROOM_STABILITY` soft scorer.

*Exit:* generated timetables have the right hours on the right days in the right room. Room
stability moves from 0% to >95%. Break and Saturday violations go to zero.

### Phase 2 — Model the lab window (4–6 days) — **the big one**
1. Re-scope `period_number` to the group; add a `lab_windows` view over `subject_assignments`.
2. `ParallelWindow` scheduling unit; `_expand_lab_batches` builds windows, not per-subject groups.
3. `_is_parallel_sibling` matches window identity, not subject. **[A1]**
4. `MAX_ONE_LAB_PER_DAY` counts windows.
5. Construct the batch↔subject rotation as a Latin square before solving; add
   `LAB_ROTATION_COMPLETE` validation.
6. Relax `SAME_SUBJECT_SAME_DAY` from always-on structural to a **configurable** rule, defaulting to
   "at most one *lecture* per subject per day, labs and tutorials exempt" — which is what the real
   data shows (160 real violations, all lecture+lab or lecture+tutorial pairings).
7. Fix `OR_TOOLS` to expand windows and propagate `batch_number`. **[A6]**

*Exit:* batch coverage 100%; lab windows carry multiple subjects; the engine can reproduce the shape
of a real TCET lab day.

### Phase 3 — Honest demand and honest allocation (3 days)
1. Use `_derive_hours()`; `_scheme_hours()` becomes the logged fallback. **[A3]**
2. Demote auto-fill to an explicit, reported `--fill-gaps` step that surfaces data gaps instead of
   inventing them.
3. **Replace the modulo teacher rotation with least-loaded assignment** (`import_tcet.py:539`).
   Sort candidates by current committed load, pick the lightest. **[A9]**
4. **Add `faculty_subject_competency`** (faculty × subject, optional preference weight). Assignment
   and `_lab_batch_faculty` may only choose from qualified teachers. **[A9, B4]**
5. **Prune profile resources** to teachers who actually hold an assignment for that division's
   subjects — expect `profile_resources` to drop from 3,710 to a few hundred. **[A9]**
6. Add `source` provenance (`GRID | SCHEME | AUTOFILL` for demand; `OBSERVED | DERIVED | INVENTED`
   for every quantity) to `subject_assignments`, `rooms.capacity`, `student_groups.strength`,
   `faculty.max_hours_*`; surface in UI. **[C5, D6]**
7. **Turn off every constraint that depends on an INVENTED quantity.** `ROOM_CAPACITY_SUFFICIENT`
   compares an invented capacity (80) against an invented strength (70); the faculty caps enforce an
   invented 8/30 on all 407 teachers. A rule fed by noise is worse than no rule — it shapes the
   timetable and you cannot tell its effect from a real constraint. Re-enable each via its
   INSTITUTIONAL toggle the day the college supplies real numbers. **[D6]**
8. Pre-solve feasibility report (demand vs. capacity per resource) that fails loudly.

*Exit:* weekly hours per (subject, division) within ±1 of the published grid; no teacher idle while
another is saturated; no constraint firing on an invented number.

### Phase 3b — Make constraints editable (2 days) **[A10]**
1. Split `STRUCTURAL_RULES` into `INVARIANT_RULES` and `DEFAULT_INSTITUTIONAL_RULES`.
2. Institutional rules fire only from a profile/college-default row; migration seeds current
   behaviour so nothing changes silently.
3. Add all 8 missing validators to the `ConstraintType` enum; add a startup assertion that the
   registry and the enum are the same set, so they can never drift again.
4. `GET /constraints/types` returns tier + a JSON-schema for each `config_json`.
5. Move every hardcoded constant out of `import_tcet.py` into institution-profile parameters. **[D2]**

*Exit:* a registrar can change "max labs per day" or the break slot in the UI, with no code change.

### Phase 4 — Solve the cohort, not the division (5–8 days)
1. Bridge: carry per-faculty day/week load from published instances into the checker. **[A4]**
2. Cohort profiles: one generation per (department, year); multi-group profiles end to end.
3. Fail-fast `is_valid`; index committed slots by resource. **[A6]**
4. Real "most constrained first": order by room scarcity × faculty scarcity × weekly hours.
5. Scoring and the preference scan on by default; always keep the best distinct attempt.
6. **Fix OR-Tools before extending it** — call `_expand_lab_batches`, propagate `batch_number`, model
   `MAX_ONE_LAB_PER_DAY`, and fix the `unplaced_count` under-report (`or_tools_solver.py:239`). **[A11, B9]**
7. **Construct-then-repair with LNS**: greedy constructs; CP-SAT re-optimises small neighbourhoods
   (a day / a division / the blockers of an unplaced session) against the full objective. **Never
   post-filter a CP-SAT answer** — every rule is modelled or enforced during construction. **[A11]**

*Exit:* zero unplaced sessions across the COMP cohort; solve time per cohort under a minute.

### Phase 5 — Prove it, and prove it stays proved (4 days)
1. The fidelity scorer of A8 as a library.
2. Golden tests: regenerate every division, score, fail CI on regression. **[A8]**
3. **Synthetic problem generator** — plant a valid timetable, derive the inputs from it, hand them to
   the solver. Any unplaced session is then provably a solver bug. Retire
   `build_synthetic_branches.py` as a scoring input. **[D4]**
4. **Second fixture college** (`fixtures/other.json`) with a deliberately different shape; CI
   generates for both. If it needs an `app/engine/` change, the overfitting is caught then. **[D3]**
5. A published-vs-generated diff report per division.
6. Re-admit IT, then the remaining branches, one at a time, each gated on the suite staying green.

### Phase 6 — Frontend (4–6 days)
1. Print stylesheet — A4 landscape, one division per page. **[C1]**
2. Redesign the parallel-batch cell as a split window. **[C2]**
3. `breakSlots` prop; required `slotTime`. **[C3, C4]**
4. Post-generation review screen: score breakdown, unplaced list with reasons, diff vs. published. **[C6]**
5. Provenance affordances. **[C5]**
6. Accessibility pass: grid semantics, keyboard nav, non-colour subject encoding; move route
   protection to middleware. **[C7]**

### Phase 7 — Security hardening (2 days)
Central role table with deny-by-default; role from DB not JWT; single DB session per request;
route-resolved auth exemptions; login rate limiting fails closed; startup assertions on
`SECRET_KEY` and `CORS_ORIGINS`. **[B-MED-3…B-LOW-6]**

---

## Answering the original question

> *is it the way we are doing it, or a data quality/quantity problem, or something else?*

**All three, in this order of blame:**

1. **Modelling (≈60%).** The lab window, the break slot, and the home room are real-world concepts
   the schema cannot express. Three hard rules actively forbid the correct answer — provably, 214
   times against the college's own published timetables. No solver can fix this.
2. **Data pipeline (≈30%).** The scraped data is a *reasonable* foundation — 46 real timetables,
   real grids, real rooms, real rotation structure. The loss happens in `import_tcet.py`, which
   throws away the derived hours it already computed, flattens everything to 3h/week, and invents
   teachers. **The data you gathered is better than the code's use of it.**
3. **Algorithm (≈10%).** Greedy with no repair, quality gated behind two opt-in flags, OR-Tools
   silently broken on batched data. Real, but it would only polish an already-wrong shape.

The good news is that the highest-impact work is also the most tractable: Phases 0–2 are roughly two
weeks and address the modelling problems, which is where the visible ugliness lives.

> *do we need more teachers / branches / data?*

**No.** Faculty utilisation is 5–32%; 279 of 407 teachers have zero assignments while two are over
cap. Rooms are 4× oversupplied. The scarcity is manufactured by a modulo assignment rotation, not by
missing data. More synthetic teachers would slow the solver and hide bugs. Fix allocation (Phase 3),
add `faculty_subject_competency`, and collect only four things from the college: **class strengths,
room capacities, the ~59 unresolved initials, and the published L/T/P scheme hours.** See A9.

> *are constraints internal or editable from outside?*

Both, and backwards. 14 rules are always-on and undisableable; **8 registered validators are not in
the API enum at all** — including `SAME_SUBJECT_SAME_DAY` and `MAX_ONE_LAB_PER_DAY`, the two that
contradict the real data most. The rules that most need tuning are the ones you cannot reach.
Phase 3b fixes this with an INVARIANT / INSTITUTIONAL / PREFERENCE tiering. See A10.

> *is there a better solver — does the Google one even work?*

It does not, on your data: **half a timetable, zero practicals, more unplaced than greedy, 5× slower**
(A11). But CP-SAT is the right engine — the integration is what's broken ("prune the domain, filter
the answer" can only lose sessions). Target: greedy constructs, CP-SAT repairs small neighbourhoods
under LNS, nothing is ever post-filtered. Fix the model before touching the solver.

> *will modelling my college break the system when anything changes?*

Only if you encode TCET's **answers**. Encoding its **vocabulary** — lab windows, break slots, home
rooms — makes the engine *more* general, because it currently cannot model any real college at all.
The real overfitting lives in `import_tcet.py`'s hardcoded constants, and Phase 3b moves them into
editable profile parameters. Then prove it with a second fixture college in CI. See Part D.

---

## Appendix — how to reproduce every number in this document

Run all four from the repo root. They are read-only.

### 1. Engine rules vs. the real published timetables — 160 / 54 / 131-of-133

```bash
python3 - <<'PY'
import json
from collections import defaultdict, Counter
tts = json.load(open('info/import/timetables.json'))['timetables']
same=tot=lab2=days=0
span=Counter(); par=Counter(); brk=Counter()
for t in tts:
    byday=defaultdict(list)
    for c in t['cells']:
        if c['kind']=='BREAK': brk[c['slot']]+=1
        if c['kind'] in ('LECTURE','LAB','TUTORIAL') and c.get('subject'):
            byday[c['day']].append(c)
    for d,cells in byday.items():
        days+=1
        for sub,n in Counter(c['subject'] for c in cells).items():
            tot+=1; same+= n>1
        if len({c['subject'] for c in cells if c['kind']=='LAB'})>1: lab2+=1
    # lab contiguity + parallel subjects per window
    lab=defaultdict(set); ds=defaultdict(list)
    for c in t['cells']:
        if c['kind']=='LAB': lab[(c['day'],c['subject'],tuple(c['batch'] or []))].add(c['slot'])
        ds[(c['day'],c['slot'])].append(c)
    for s in lab.values():
        o=sorted(s); r=b=1
        for x,y in zip(o,o[1:]): r=r+1 if y==x+1 else 1; b=max(b,r)
        span[b]+=1
    for v in ds.values():
        L=[c for c in v if c['kind']=='LAB']
        if L: par[len({c['subject'] for c in L})]+=1
print(f'SAME_SUBJECT_SAME_DAY violated by real data: {same} of {tot}')
print(f'MAX_ONE_LAB_PER_DAY  violated by real data: {lab2} of {days}')
print(f'lab contiguous-run lengths: {dict(span)}   (2h blocks are forced by the importer)')
print(f'distinct lab subjects per window: {dict(par)}')
print(f'BREAK slot positions: {dict(brk)}')
PY
```

### 2. Current output quality — unplaced, room churn, Saturday, break-slot usage

```bash
.venv/bin/python - <<'PY'
from app.database import SessionLocal
from sqlalchemy import text
db=SessionLocal(); q=lambda s: db.execute(text(s)).fetchall()
print('runs with unplaced:', q("select count(*) from timetable_generations where placement_warning is not null")[0][0], 'of', q("select count(*) from timetable_generations")[0][0])
print('lecture pairs split across rooms:', q("""select count(*) from (select g.name,s.subject_id from timetable_slots s
  join student_groups g on g.id=s.student_group_id where s.session_type='LECTURE'
  group by 1,2 having count(distinct s.room_id)>1) t""")[0][0], 'of',
  q("""select count(*) from (select g.name,s.subject_id from timetable_slots s
  join student_groups g on g.id=s.student_group_id where s.session_type='LECTURE' group by 1,2) t""")[0][0])
print('Saturday slots:', q("select count(*) from timetable_slots where day_of_week=5")[0][0])
print('slots in the BREAK row (slot 4):', q("select count(*) from timetable_slots where slot_number=4")[0][0])
print('(subject,group) with >1 assignment row:', q("""select count(*) from (select subject_id,group_id
  from subject_assignments where batch_number is null group by 1,2 having count(*)>1) t""")[0][0])
print('rooms per division (top 3):', q("""select g.name, count(distinct s.room_id) from timetable_slots s
  join student_groups g on g.id=s.student_group_id group by 1 order by 2 desc limit 3"""))
db.close()
PY
```

### 3. Faculty utilisation — 5–32%, 279 idle, 2 over cap

```bash
.venv/bin/python - <<'PY'
from app.database import SessionLocal
from sqlalchemy import text
db=SessionLocal()
for r in db.execute(text("""
 with dem as (select g.department d, sum(sa.weekly_hours) h, count(distinct g.id) n
   from subject_assignments sa join student_groups g on g.id=sa.group_id group by 1),
 fac as (select department d, count(*) n, sum(max_hours_per_week) cap from faculty group by 1)
 select dem.d, dem.n, dem.h, fac.n, fac.cap, round(100.0*dem.h/fac.cap,0)
 from dem join fac on fac.d=dem.d order by 6 desc""")):
    print(f'  {r[0][:34]:34} divs={r[1]:3} demand={r[2]:4}h teachers={r[3]:3} cap={r[4]:5}h util={r[5]:3}%')
print(db.execute(text("""select count(*) filter (where u=0) idle, count(*) total from
  (select f.id, count(sa.id) u from faculty f left join subject_assignments sa on sa.faculty_id=f.id group by 1) t""")).fetchone())
print('over cap:', db.execute(text("""select f.name, sum(sa.weekly_hours), f.max_hours_per_week from faculty f
  join subject_assignments sa on sa.faculty_id=f.id group by f.id having sum(sa.weekly_hours)>f.max_hours_per_week""")).fetchall())
db.close()
PY
```

### 4. Greedy vs OR-Tools on real profiles — zero practicals from CP-SAT

```bash
.venv/bin/python - <<'PY'
import time
from sqlalchemy import select
from app.database import SessionLocal
from app.engine.profile_resolver import ProfileResolver
from app.engine.solvers.greedy_solver import GreedySolver
from app.engine.solvers.or_tools_solver import ORToolsSolver
from app.models.generation import VariationMode
from app.models.profiles import TimetableProfile
db=SessionLocal()
for name in ["Computer Engineering — COMP-TE-D","Computer Engineering — COMP-SE-A"]:
    p=db.scalars(select(TimetableProfile).where(TimetableProfile.name==name)).first()
    if not p: continue
    rp=ProfileResolver(db).resolve(p.id,None); print(f'\n{name}')
    for cls,lbl in ((GreedySolver,'GREEDY'),(ORToolsSolver,'OR-TOOLS')):
        s=cls(db=db,profile=rp,instance_id=999,seed=None,variation=VariationMode.RANDOM)
        s.reserved_conflicts={}; t=time.time(); slots=s.solve(); dt=(time.time()-t)*1000
        labs=sum(1 for x in slots if str(getattr(x.session_type,'value',x.session_type))=='LAB')
        b=sorted({x.batch_number for x in slots if x.batch_number is not None})
        print(f'  {lbl:9} {len(slots):4} slots {labs:3} lab  unplaced={s.unplaced_count:3} batches={b or "NONE"} {dt:6.0f}ms')
db.close()
PY
```

### 5. The tests pass anyway — see A8

```bash
uv run python -m app.tests     # 216/216 green while every metric above is red
```
