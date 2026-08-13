# Timetable audit — generated vs real TCET (2026-08-12)

A ground-truth audit of the timetables the generator produces, compared against the
college's **actual** class timetables. Sources:

- Real ground truth: `sample/timetable_info_TE_FE.md` — the genuine **COMP D Sem II (FE,
  ES&H dept)** and **COMP D Sem VI (TE, COMP dept)** class timetables, in canonical
  `DAY → TIME → ACTIVITY → BATCH → ROOM` form; plus the scheme PDFs in `sample/`
  (Sem 3/4/5/6/7/8) and the COMP faculty list.
- Generated output: the live published instances in the DB (192 classes, ~4700 slots),
  e.g. `COMP-FE-A`, `COMP-TE-D`.

Rules the founder stated (treated as truth):

1. FE classes split into **3 batches**; SE/TE/BE into **2 lab groups** (4 batches D1–D4
   paired as D1D2 / D3D4). Practicals run in **parallel**: every batch is in a lab at the
   same time, each on a different subject (FE) or the same/different subject (SE+), 2h
   blocks.
2. A class gets **at most one practical (lab) subject per day**.
3. The timetable **structure changes every year** — timings, break placement (short +
   long, long only), lecture duration all vary by year/semester.
4. Subjects **not in the syllabus are fillers** (Notional Learning, Indian Constitution,
   SSIC, AAD, IKS, PS-I/IV, IP, PBL, DA, workshops). Fillers may be online, batch-based,
   Saturday-only, or merged multi-period blocks — not ordinary lectures.
5. Some lectures are **online** (e.g. IC in TE) — no physical room.

---

## 1. How a timetable is currently generated (the pipeline)

1. **Seed data** (`scripts/seed_demo.py`) creates: divisions (`COMP-FE-A` …), subjects
   split into lecture/tutorial/lab **streams**, faculty, rooms, and
   `subject_assignments` (subject → faculty → group, `weekly_hours`).
2. **Profile** (`timetable_profiles` + `profile_resources` + `profile_parameters` +
   `hard_constraints`) is the solver's whole input contract: which rooms/faculty/groups/
   subjects are in scope, the time grid (`slots_per_day`, `day_start_time`,
   `slot_duration_minutes`, `lunch_break_after_slot`, `working_days`), and rules
   (`CONTIGUOUS_LAB_SLOTS` for 2h lab blocks).
3. `POST /generate` → `Scheduler`:
   - `ProfileResolver` merges the profile (or combination).
   - `_load_published_conflicts` reserves every PUBLISHED instance's faculty/room/group
     at (day, slot) so new timetables cannot clash with live ones.
   - For each requested instance, `GreedySolver.solve()`:
     - `_build_sessions` expands every assignment into `weekly_hours` sessions; lab
       subjects expand into 2h contiguous blocks.
     - `_build_slot_times` builds **one** slot grid shared by every day.
     - for each session, scan `(day, slot)` × matching rooms; commit the first placement
       that passes `ConstraintChecker` (double-book, capacity, room requirements,
       unavailability, blackouts, max hours/day & week, same-subject-same-day,
       cross-timetable reservations, registry rules).
   - Instance soft-scored, diversity-filtered, "best" selected.
4. Admin selects + publishes an instance; it then reserves its slots for all future runs.
5. Exports: per-group PDF grid, CSV, iCal.

**What the solver is:** a deterministic first-fit greedy over a weekly template. It has no
concept of batches, parallel sessions, per-day grids, filler activities, online lectures,
or subject room stability.

---

## 2. Audit findings

Severity: 🔴 blocks correctness of a real timetable · 🟠 visibly wrong · 🟡 cosmetic.

### A. The data model / seed does not match the college

| # | Finding | Evidence (real → generated) | Severity |
|---|---------|-----------------------------|----------|
| A1 | **FE is modelled as part of every department, not as its own ES&H department.** | Real: FE is `Department of Engineering Sciences & Humanities`, one shared cohort (rooms 508/518/530, lab rooms 216/006/418/519/715). Generated: `COMP-FE-A`, `IT-FE-A`, … each with `department="Computer Engineering"` and its own duplicate FE subject set. | 🔴 |
| A2 | **FE subjects are invented, not the real Sem II scheme.** | Real FE: Maths-II, Chemistry, PPS, Engineering Mechanics (main); IKS, AAD-II, PS-I, ELEC WS / PC ASBLY WS, Notional (fillers). Generated `COMP-FE-A`: Engineering Physics, Basic Electrical & Electronics, Communication Skills, Engineering Drawing, Engineering Maths-I. | 🔴 |
| A3 | **TE/BE subject scheme differs from the real scheme** (partly sem-odd/even mismatch, partly wrong streams). | Real TE (Sem VI): CG/MP/IIS/TOC + SSIC, IC, PS-IV, IP, PBL, DA, Notional. Generated TE (Sem V) invents an "Intelligent Systems Lab", has no IP/PBL/DA/Notional, and treats SSIC/IC as normal classroom lectures. | 🟠 |
| A4 | **Class strength is wrong.** | Real FE COMP-D strength 63; seed sets 60 everywhere. Capacity checks then allow undersized rooms. | 🟡 |
| A5 | **Fillers are not distinguishable from main subjects.** | A filler is a plain `Subject` row, so the solver schedules IC/SSIC as ordinary 1h classroom lectures; real IC is **online**, Notional is a **merged 3h+ block**, PS-IV/DA are **batch** activities, IP/PBL are **Saturday** activities. No flag exists for online / notional / activity. | 🔴 |

### B. The engine cannot express the college's real rules

| # | Finding | Evidence | Severity |
|---|---------|----------|----------|
| B1 | **No batch layer — practicals are whole-division blocks.** | Real TE: `CG Lab D1D2 / IIS Lab D3D4` run **in parallel** in 2 rooms at 12:30, then the halves swap. Real FE: `PPS/CHEM/EM | B1/B2/B3 | 216/006/418` — 3 parallel labs. Generated `COMP-TE-D`: `Intelligent Systems Lab` = one 2h block for all 60 students in one room; no split, no parallelism, no room concurrency. | 🔴 |
| B2 | **No parallel-session scheduling.** | The solver places one session at a time and double-books rooms/faculty/groups. Nothing can say "these N sessions must occupy the same time window in different rooms" — the defining property of a real practical period. | 🔴 |
| B3 | **Max-one-lab-per-day is not enforced.** | Only `SAME_SUBJECT_SAME_DAY` exists (blocks the *same* subject twice). Two *different* lab subjects on one day are legal. Real rule (founder + TE evidence): each batch gets at most one practical subject per day. | 🔴 |
| B4 | **One time grid for all days and all years.** | Real FE: 08:00–18:30, 15-min breaks, Monday lunch 14:15, Tue–Fri lunch 13:15, a 16:15 transition, and a **different** Saturday. Real TE: 8:30–17:30, break at T4. Structure changes every year. The engine has a single `slots_per_day`/`lunch_after` grid per profile and no per-day override. | 🔴 |
| B5 | **Labs consume the same slot budget as lectures; hours come out wrong.** | Real TE direct-contact ≈ 35 h/week (16 theory + 1 tutorial + 8 practical + fillers + Saturday 7). Generated `COMP-TE-D` = 25 sessions ending at 12:30; `COMP-FE-A` = 24. | 🟠 |
| B6 | **No "online session" concept.** | No field on a slot/session for "online, no room". Real IC (TE) is online. | 🟠 |
| B7 | **No room affinity / stable homerooms.** | Real: CG → 718/610, TOC → 608, IIS → 610/718, Maths-II → 518, PPS → 530/508. Generated `COMP-TE-D`: Computer Graphics across `COMP-CR10/CR4/CR9`, TOC across `COMP-CR10/CR12/CR16`, MP across `COMP-CR10/CR14/CR7`. A subject bounces rooms every lecture. | 🟠 |
| B8 | **Teacher-subject load is unrealistic.** | Real TE: SuS teaches only CG, SPS only IIS, TN only MP, VS only TOC. Generated: every teacher carries 3–4 subjects (dedicated-team seed hack), which also makes per-teacher week blocks unrealistic. | 🟠 |

### C. Output shape — what a human sees

| # | Finding | Evidence | Severity |
|---|---------|----------|----------|
| C1 | **Every class finishes by 12:30 PM.** | Generated uses only slots 1–4 (08:30–12:30) + the rare slot 5 — the "pack mornings" behaviour from a previous session. Real FE runs to 18:30, TE to 17:30. The entire afternoon and evening are empty. | 🔴 |
| C2 | **Saturday has normal lectures.** | Real FE Saturday = IKS + AAD-II + Notional; real TE Saturday = IP/PBL/co-curricular. Generated `COMP-FE-A` has 4 normal lectures on Saturday. | 🟠 |
| C3 | **No Notional Learning / merged filler blocks.** | Real timetables show a merged `08:00–11:15` (FE) or `08:30–09:30` (TE) Notional block, and PS/IP/PBL/DA batch activities. Generated output has none. | 🟠 |
| C4 | **The lunch break sits between slot 4 and 5 but no afternoon follows.** | The seed's `lunch_break_after_slot=4` plus morning-packing means lunch is immediately before "end of day". The FE grid (08:00 start, 15-min break at 10:00, lunch 13:15) and TE grid (break at 11:30) are both unrepresentable. | 🟡 |

---

## 3. Root causes

1. **Batches are not entities.** `StudentGroup.group_type` has a `BATCH` value but nothing
   creates batch rows or schedules against them; the solver's unit is the division.
2. **"Practical" is a room flag, not a split.** A lab is "a 2h block for the whole class";
   the real unit is "a 2h parallel period where every batch is doing a different lab".
3. **The seed is a demo, not the college.** FE under every department, invented subjects,
   fabricated 176-faculty teams, strength 60.
4. **The time grid is one-size-fits-all.** Real grids vary per year *and* per day.
5. **Room and teacher realism were optimised away** (room pool assigned per session;
   dedicated per-class faculty teams) to make the previous generation look "clean".

## 4. Fix roadmap (maps to the DD-024/DD-025 design work)

1. **ES&H / FE department** — FE becomes its own department ("Engineering Sciences &
   Humanities") with the real Sem I/II scheme (Maths, Chemistry, PPS, EM + fillers), real
   strength, real FE divisions; engineering departments keep SE/TE/BE only. *Data + seed.*
2. **Batch layer** — batch `StudentGroup` rows under each division (3 for FE, 4 for SE+),
   teacher-maintained (DD-025). *Schema + seed + UI.*
3. **Parallel practical engine** — a session group: N lab sessions (one per batch) that
   must occupy the same time window in different rooms; the solver allocates the window
   and rooms together, rotates batches across subjects, and enforces max-one-lab/day per
   batch. *Engine + registry rule.*
4. **Per-day time grids** — `{day_of_week: slots[]}` so FE/TE structure and yearly changes
   are profile data. *Engine.*
5. **Session kinds** — `LECTURE / TUTORIAL / LAB / ACTIVITY / NOTIONAL / ONLINE` with
   room-optional online sessions and merged notional blocks. *Schema.*
6. **Realism** — real faculty, real rooms, subject room affinity, one-subject-per-teacher
   ties. *Data.*
