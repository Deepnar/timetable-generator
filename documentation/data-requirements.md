# Data requirements — what is real, what is invented, and what we must eventually collect

**Date:** 2026-08-15 · Companion to `system-audit-and-plan.md` (Part D6) and DD-031.

Two questions answered here, both measured rather than estimated:

1. **If we disable the constraints driven by invented data, how much does today's output change?**
   → **Nothing at all.** They reject zero candidates. Measured below.
2. **What real information will we eventually need, and what breaks until we have it?**
   → The ledger in §3, ordered by payoff.

---

## 1. The measurement: which constraints actually bind

Instrumenting `ConstraintChecker.check_all` across a real solve of COMP-SE-A and COMP-TE-D —
**31,370 candidate evaluations, 20,170 rejections**:

| Rule that rejected the candidate first | rejections | share |
|---|---:|---:|
| `NO_GROUP_DOUBLE_BOOK` | 14,370 | 71.2% |
| **`SAME_SUBJECT_SAME_DAY`** | 2,172 | **10.8%** |
| **`MAX_ONE_LAB_PER_DAY`** | 1,890 | **9.4%** |
| `NO_TEACHER_DOUBLE_BOOK` | 1,168 | 5.8% |
| `NO_ROOM_DOUBLE_BOOK` | 570 | 2.8% |
| `ROOM_CAPACITY_SUFFICIENT` | **0** | **0.0%** |
| `FACULTY_MAX_HOURS_PER_DAY` | **0** | **0.0%** |
| `FACULTY_MAX_HOURS_PER_WEEK` | **0** | **0.0%** |

**All three invented-data rules are completely inert.** Not "low impact" — they never fire once in
31,370 evaluations. Why:

- `ROOM_CAPACITY_SUFFICIENT` — invented capacity (80 classroom) always exceeds invented strength
  (63–70), and batch slots skip the check entirely (`constraint_registry.py:589`). It can never fail.
- `FACULTY_MAX_HOURS_*` — the caps count only `committed`, i.e. **this division's** slots
  (`constraint_registry.py:645, 664`). No single division loads one teacher near 30h/week, so the
  cap is never approached. (This is also why A9 found two teachers at 33h **college-wide** against a
  30h cap: the rule is simultaneously fabricated *and* unenforced.)

### The counterfactual — unplaced sessions across 5 real divisions

| Configuration | unplaced per division | total |
|---|---|---:|
| as-is (today) | `[6, 2, 1, 7, 6]` | **22** |
| **without the 3 invented-data rules** | `[6, 2, 1, 7, 6]` | **22** *(no change)* |
| without `SAME_SUBJECT_SAME_DAY` | `[6, 2, 1, 7, 6]` | 22 |
| **without `MAX_ONE_LAB_PER_DAY`** | `[2, 0, 0, 0, 6]` | **8** |
| without both reality-contradicting rules | `[2, 0, 0, 0, 6]` | **8** |

### What this means

- **Turning off the invented-data rules is a zero-risk change to today's output.** It removes three
  landmines without moving a single session. Do it in Phase 3 with confidence.
- **One line in `import_tcet.py:615` causes 64% of unplaced sessions.** `MAX_ONE_LAB_PER_DAY` —
  a rule the real timetable violates 54 times — accounts for 14 of 22. Removing it is not the
  correct fix on its own (Phase 2's lab-window model is), but it quantifies the damage.
- **`SAME_SUBJECT_SAME_DAY` costs quality, not feasibility.** It never leaves a session unplaced —
  the solver finds another day. What it does is force a subject's lecture and its practical onto
  different days, which is precisely the shape the real timetable does *not* have. It is 10.8% of
  all rejections, so it is heavily steering the result.

**The landmine to remember:** these three rules are inert *because* the numbers are invented. The
day real capacities arrive (a 66-seat classroom against a 70-student division) `ROOM_CAPACITY_SUFFICIENT`
starts firing hard. The day cohort solving lands (Phase 4), faculty load composes across divisions
and the caps start firing hard. **Both must be switched on deliberately, with real data, and
re-measured** — not left on by default running on placeholders.

---

## 2. Provenance ledger — what is real today

| Entity | in DB | real | invented | invented fields |
|---|---:|---|---|---|
| rooms | 205 | 61 names (30%) | **144 (70%)** | **100% of capacities** (80/60/45 defaults); `room_type` is *derived* from lab usage, not published |
| faculty | 407 | 38 names (9%) | **369 (91%)** | **100% of `max_hours_per_week`/`_per_day`** (30/8 for everyone) |
| student_groups | 36 | names real | — | **100% of strengths** (`{1:63, 2:63, 3:70, 4:60}`) |
| subjects | 149 | names + codes real | — | **100% of `hours_per_week`** (flat 3/2/1) |
| subject_assignments | 540 | subject↔group pairing real | — | **100% of `weekly_hours`**; teacher real only where an initial resolved |

**Fully real:** `info/import/timetables.json` (46 published grids, 2,451 cells) and
`info/import/grids.json` (slot times, working days). Everything else is a real *name* with an
invented *quantity* attached.

Faculty initials resolve as: **38 named · 29 ambiguous** (several people share an initial) ·
**59 unresolved** (initial appears in a grid, never in any glossary).

---

## 3. What we must eventually collect — ordered by payoff

### 🔴 Tier 1 — blocks correctness. Ask for these first.

**1. Per-subject L/T/P scheme hours** (lecture / tutorial / practical hours per week, per subject,
per semester).
- *Why:* the single most important number in the system. It defines how much must be scheduled.
- *Today:* 100% invented — a flat 3h for every lecture subject via `_scheme_hours`.
- *Breaks without it:* demand is wrong by up to 4×, which is a direct cause of unplaced sessions.
- *Where to get it:* **already in your possession.** The syllabus and scheme PDFs in `sample/`
  (`(Scheme) Sem V-1.pdf`, `SEM 3 Scheme-1.pdf`, etc.) are the published L/T/P tables. Extracting
  them is roughly a day of work and needs nothing from the college.
- *Interim:* `_derive_hours()` already computes this from the published timetables and is currently
  computed-and-discarded. Use it (Phase 3) — it is a good approximation until the scheme is parsed.

**2. Class strengths** — students per division.
- *Today:* 100% invented.
- *Breaks without it:* `ROOM_CAPACITY_SUFFICIENT` is meaningless; lab batch counts cannot be derived
  (currently hardcoded 3 for FE, 2 otherwise); room allocation cannot be validated.
- *Where:* the registrar. One number per division — 36 numbers. **Cheapest high-value item on this list.**

**3. Room capacities + a room inventory** — seats per room, and which rooms are labs.
- *Today:* 100% invented; `room_type` inferred from usage, so any lab never used in a scraped grid
  is misclassified as a classroom.
- *Breaks without it:* capacity checking is fiction; lab-room supply cannot be verified.
- *Where:* facilities/estate office. ~84 real rooms.

**4. The 59 unresolved faculty initials** (+ disambiguating the 29 ambiguous ones).
- *Today:* each becomes a synthetic placeholder with a generated Indian name.
- *Breaks without it:* the timetable names people who do not exist — fatal for credibility the
  moment a real teacher reads it.
- *Where:* the department glossary the initials come from. This is a lookup table, not a project.

### 🟠 Tier 2 — unlocks correctness once cohort solving lands (Phase 4)

**5. Real faculty workloads** — actual max hours/week and /day, per teacher, and any
part-time/visiting status.
- *Today:* 30h/8h for all 407.
- *Note:* inert today (see §1), but becomes load-bearing the moment load composes across divisions.

**6. Faculty–subject competency** — who is qualified to teach what.
- *Today:* does not exist; any department teacher can be assigned any department subject, which is
  how `_lab_batch_faculty` can hand a practical to someone who has never taught it.
- *Why it matters:* this is the highest-value **new** structure in the whole list. It is what stops
  the system inventing plausible-but-wrong staffing.
- *Where:* HoD per department. A checkbox grid of teachers × subjects.

**7. Faculty unavailability** — genuine constraints (admin duties, part-time days, research slots).
- *Today:* the table exists and is empty.
- *Note:* date-bounded rows are **silently inert** unless the profile sets `term_start`
  (`constraint_registry.py:454`) — a trap worth knowing before this data arrives.

**8. Home-room / venue allocation** — which classroom each division owns.
- *Partly available:* the `venue` field in the scraped timetables (e.g. `718/608/610`) already
  carries it and is parsed but only used as a sort order. Phase 1 makes it binding.

### 🟡 Tier 3 — fidelity and completeness

**9. Per-division break slot** — derivable from the scraped BREAK cells (slot 3/4/5/6 varies), so
this is not a data request, just correct use of what we have. Confirm the pattern with the registrar.

**10. Saturday policy per programme** — the grids say `working_days: [0..5]` but also label Saturday
`"IP / co-curricular / notional learning"`. Only 11 of 46 divisions have any Saturday teaching.
Needs one policy statement per programme.

**11. ACTIVITY / IP / PBL / notional-learning blocks** — **629 ACTIVITY cells** across the real
timetables, the second-largest category, and the engine models none of them. Also 221 NOTIONAL and
587 FREE cells: real timetables are ~35% empty *by design*, while the engine packs everything.

**12. Online / no-room subjects** — `is_online` exists in the import format; online subjects
currently fall back to occupying a physical classroom.

**13. Elective / OE group structure** — how students split across electives, which determines whether
an elective is one session or several parallel ones.

---

## 4. Branch coverage — what exists at the college vs what is in the system

| Branch | divisions | grid | timetables | subjects | assignments | status |
|---|---:|---|---:|---:|---:|---|
| COMP | 11 | ✅ | 11 | 21 | 166 | **imported** — the only branch with a real roster |
| IT | 10 | ✅ | 10 | 20 | 169 | **imported** — partial real data |
| EXTC | 6 | ✅ | 6 | 28 | 21 | **imported** — thin assignments |
| E&CS | 3 | ✅ | 3 | 22 | 15 | **imported** — shape only, no published faculty |
| MECH | 3 | ✅ | 3 | 19 | 18 | **imported** — shape only |
| CIVIL | 3 | ✅ | 3 | 20 | 17 | **imported** — shape only |
| **AI&ML** | 2 | ✅ | 2 | 0 | 0 | excluded — *has grids and timetables already* |
| **BCA** | 2 | ✅ | 2 | 19 | 21 | excluded — *has grids, timetables, subjects AND assignments* |
| **MCA** | 1 | ✅ | 1 | 10 | 5 | excluded — *has data* |
| **ES&H** | 1 | ✅ | 1 | 5 | 0 | excluded — **owns all of FE (first year)** |
| MBA | 4 | ✗ | 4 | 67 | 0 | excluded — timetables + 67 subjects, no grid |
| AI&DS, IoT, CSE-IoT, CS&E, MME | 0 | ✗ | 0 | 0 | 0 | **no data at all** |

### The two things worth knowing here

**BCA, MCA and AI&ML already have usable data and are excluded anyway.** `REAL_DATA_CODES`
(`import_tcet.py:45`) is a hardcoded set that drops them. BCA in particular has grids, timetables,
subjects *and* 21 assignments — as much as MECH or CIVIL, which are imported. Re-admitting them is a
one-line change once the fidelity suite exists to prove it does no harm.

**ES&H is the biggest structural gap.** It owns **all of first year** — every branch's FE students —
with 18 labs and 14 classrooms of its own. FE is the largest cohort in the college and is currently
represented by a single group with zero assignments. FE also has a genuinely different shape
(3 lab batches instead of 2, a different daily grid, online Saturday sessions), so it is not just
"more of the same" — it will exercise parts of the engine nothing else does.

**AI&DS, IoT, CSE-IoT, CS&E and MME have nothing.** They exist at the college and publish no grids.
They need manual entry, and they are the **lowest** priority: adding breadth to a system that is not
yet correct on the branches it has would only make bugs harder to attribute.

---

## 5. The rule that keeps all of this safe

> **No constraint may depend on a field whose provenance is `INVENTED`.**

This is what makes the "our data is fake, will the system break on real data?" worry go away:

- If a rule never runs on invented numbers, real numbers arriving cannot change a result that was
  never based on them.
- Every fidelity metric in the audit (room stability, batch coverage, break-slot usage, Saturday
  load, hours per subject, teachers per subject) is derivable from `timetables.json` alone and uses
  **zero** invented quantities. That is deliberate.
- Each quantity gets a provenance tag (`OBSERVED` / `DERIVED` / `INVENTED`) in Phase 3. A constraint
  whose inputs are all `INVENTED` refuses to activate and says so.

The corollary is the useful part: **collecting data is not a prerequisite for building the engine.**
Items 1–4 above make the timetable *true*; none of them are needed to make it *correct*. Build
against the scraped timetables, which are real, and let the data arrive when it arrives.
