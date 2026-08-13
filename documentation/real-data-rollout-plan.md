# Real-data rollout plan — align the repo with the actual TCET ground truth

> **Status (14 Aug 2026):** the machine-readable import is **built and live**, scoped to
> the 6 branches with published grids (COMP/IT/EXTC/E&CS/MECH/CIVIL). `import_tcet.py`
> seeds Postgres from `info/import/*.json` + `info/import/synthetic_branches.json`
> (**branch-bound faculty pools ~40/branch**, per-branch rooms, real scheme hours,
> retire-own-published-on-republish). `generate_college.py` publishes **all 36 classes
> (~1,220 slots, morning-filled, parallel labs)**. Unplaced sessions dropped to ~90
> (mostly COMP/IT SE classes legitimately near the 54-slot weekly cap). Frontend grid
> renders parallel batches stacked with `B{n}` badges and scrolls instead of overlapping.
> Remaining: per-day grids, online/notional kinds, placement-report reasons (P3), the
> ambiguous faculty initials + branches with no grids (college data).

This plan consolidates everything learned from the **`info/` scraped website pack**
(crawled 13 Aug 2026) and the `sample/` PDFs, and lays out every fix needed so the
timetable-api produces timetables that match how TCET actually works.

**Ground-truth sources (ranked):**
1. `info/03-timetables/class/UG/` — 55 vision-verified UG division timetables
   (SE/TE/BE COMP A–D, IT, EXTC, E&CS, MECH, CIVIL, AI&ML, BCA, MCA, MBA) + FE grids
   under `humanities-sciences/`.
2. `info/04-faculty-directory.md` + `info/02-departments/*/faculty.md` — real people.
3. `info/05-courses-and-results.md` — real subject lists per semester (560 result registers).
4. `info/01-institute/` — academic calendar, academics, leadership, exams.
5. `info/02-departments/` — real labs, classrooms, room counts per branch.
6. `sample/timetable_info_TE_FE.md` — the founder-supplied FE COMP-D Sem II and
   TE COMP-D Sem VI grids (already transcribed into this plan).

---

## 1. What the ground truth actually says

### 1.1 The real institution

- TCET (Thakur College of Engineering & Technology), Mumbai. Autonomous, NBA/NAAC "A".
- Programs: 21 UG, 11 PG, 5 PhD. B.E./B.Tech 4-year + FE common first year.
- Principal Dr. B.K. Mishra; VP Dr. R.R. Sedamkar; Dean Academic Dr. Sheetal Rathi.
- Timetable approval chain (the real DRAFT→SELECTED→PUBLISHED workflow):
  Prepared (APs) → HOD → Dean Academic → VP → Principal.
- Academic year: odd sem Jun–Dec, even sem Jan–May. Even-semester start **2 Jan 2027**.
- AY 2026-27 odd sem: 90 instructional days; ISE-I 13–15 Jul; ISE-II 22–25 Aug;
  Ganapati closure 15–19 Sep; Zephyr fest 29 Sep–1 Oct; ATKT 3–14 Aug.
- Hard rule from the calendar: each faculty **min 42 lectures + 10 practical/tutorial
  sessions per semester**.

### 1.2 Real departments (the seed's 12 are wrong — 5 are fabricated)

Real UG engineering branches + the FE department:

| # | Department | Site code | Est. | Faculty | Labs | Rooms |
|---|---|---|---|---|---|---|
| 1 | Computer Engineering | COMP | 2002-03 | 39 (roster lists 65) | 6 UG + 1 PG + PhD | 5 UG CR + PG CR + 1 tutorial |
| 2 | Information Technology | IT | 2002-03 | 32–42 | 6 | — |
| 3 | Electronics & Telecommunication | EXTC | 2002-03 | 23–29 | — | — |
| 4 | Electronics & Computer Science | E&CS | 2008-09 | 10 | 9 | — |
| 5 | Mechanical Engineering | MECH | 2012-13 | 16 | 10 | — |
| 6 | Civil Engineering | CIVIL | 2015-16 | 14 | 7 | — |
| 7 | CSE — Cyber Security | CS&E | — | — | — | — |
| 8 | Mech & Mechatronics (Additive Mfg) | MME | 2022-23 | 10 | 3 | — |
| 9 | B.Tech AI & ML | AI&ML | 2020-21 | 8–23 | 3 | — |
| 10 | B.Tech AI & Data Science | AI&DS | 2020-21 | 27+2 | 4+1 | — |
| 11 | B.Tech Internet of Things | IoT | 2020-21 | 11 | 3 | intake 30 |
| 12 | B.Tech CSE (IoT) | CSE-IoT | 2021-22 | 9 | 3 | intake 120 |
| 13 | **Engineering Sciences & Humanities (ES&H / HNS)** | HNS | 2008-09 | **77–88** | **18** | **14 CR + 4 seminar + 1 auditorium** |

Non-engineering (out of the timetable product's core scope, but exist):
BCA, BBA, B.Voc, MCA, MBA.

**The current seed's departments `ELX` (Electronics Engg), `ELEC` (Electrical Engg),
`CHEM` (Chemical Engg), `INST` (Instrumentation), `CSBS` are FABRICATED** — none exist
at TCET. The seed is missing E&CS, CS&E, MME, IoT, CSE-IoT, and ES&H-as-owner-of-FE.

### 1.3 FE is ES&H, and FE has two streams

- **Every department's first year is taught by the ES&H department** (confirmed by the
  real FE COMP-D header: "Department of Engineering Sciences & Humanities").
- FE divisions are named by intake (COMP A/B/C/D, …); **division count varies per
  department and per intake** (COMP had 3 last year, 4 this year; MECH may have 1).
- **FE two-stream system:** departments split into two groups that start on opposite
  subject streams:
  - **Group I** (COMP, CSE-CS, CIVIL, CSE-IoT, AI&DS) start on the **Physics stream**.
  - **Group 2** (IT, MECH, E&TC, E&CS, MME, AI&ML) start on the **Chemistry stream**.
  - The streams swap in the even semester. (Sources: the two "Syllabus Group" PDFs;
    the founder; FE Sem-II exam register listing Maths-II/PPS/EM/IKS + BEE/EGD/Comm.)
- **FE Sem II (Chemistry stream) real scheme** (from the real COMP-D FE timetable +
  result registers):
  - Mathematics-II: 4 lectures + 1 tutorial
  - Chemistry: 4 lectures + 2h practical
  - Programming for Problem Solving (PPS): 4 lectures + 2h practical
  - Engineering Mechanics: 4 lectures + 2h practical
  - Fillers: IKS (1 lect + 2h practical + Sat), AAD-II (Sat), PS-I (2h, 2 batches),
    ELEC WS / PC ASBLY WS (2h, 2 batches), Notional Learning (merged 08:00–11:15).
- **FE Sem I (Physics stream) real scheme** (from the Syllabus Group-I PDF + registers):
  - Engineering Mathematics-I (3T + 1 Tut), Physics (3T + 2P),
    Basic Electrical Engineering (3T + 2P), Engineering Graphics & Design (2T+4P),
    English for General & Professional Communication (2T+2P);
    fillers AAD-I, Workshop & Mfg Practices-I, Notional.
- FE COMP real strength: **63** (not 60). Lateral/direct-SE admissions raise SE strength.

### 1.4 Real UG division structure (AY 2026-27 odd)

| Branch | Divisions |
|---|---|
| COMP | SE A–D, TE A–D, **BE A–C** |
| IT | SE A–D, TE A–C, BE A–C |
| EXTC | SE A–B, TE A–B, BE A–B |
| E&CS | SE, TE, BE |
| MECH | SE, TE, BE |
| CIVIL | SE, TE, BE |
| MME | SE, TE, BE |
| AI&ML | S.T. A–C (links dead), T.T., B.T. |

So division count is **not** uniformly 4 — BE often has 3, smaller branches 1–2 per year.

### 1.5 The real grids (per year, and they differ)

| Level | Grid | Break | Saturday |
|---|---|---|---|
| FE | 08:00–18:30, ~12 buckets, 15-min break 10:00, lunch 13:15 (Mon 14:15), 16:15 transition | short + long | IKS + AAD + **online** IE/ISE |
| SE/TE | 8:30–5:30, 9 periods | T4 (11:30–12:30) | IP / co-curricular / notional |
| BE | 8:30–5:30, 38 hrs/week | T4 | **none**; 5th theory lecture **online** |

Structure changes **every year** (founder). The engine needs **per-day, per-profile grids**.

### 1.6 Batches & parallel practicals (the defining rule)

- **FE: 3 batches** (B1/B2/B3); parallel 2h practicals, each batch on a **different**
  subject at the same time, rooms distinct (e.g. `PPS/CHEM/EM | B1/B2/B3 | 006/519/315`),
  rotating so every batch does every lab once a week.
- **SE/TE/BE: 4 batches D1–D4 paired as 2 lab groups (D1D2 / D3D4)**; parallel 2h labs,
  same or different subject per group, distinct rooms (e.g. `CG Lab D1D2` ∥ `IIS Lab
  D3D4`; `MP Lab D1D2` ∥ `MP Lab D3D4`).
- **Max one practical subject per day** per group.
- Fillers use other batch splits: PS-IV = 6 batches, DA = 3 batches (TE), PS-I/WS = 2 (FE).

### 1.7 Real subjects per semester (COMP, from result registers + timetables)

- FE Sem I (HME 2023): Physics, Mathematics-I, Basic Electrical Engineering,
  Engineering Graphics & Design, (Communication), AAD-I, Workshop-I.
- FE Sem II: Chemistry, Mathematics-II, Engineering Mechanics, (PPS, IKS),
  AAD-II, Workshop-II, Summer Internship.
- SE Sem III: Universal Human Values-II, Mathematics-III, Digital Logic Design &
  Computer Architecture, Database Management System, Data Structure using Java,
  Professional Skills-II, Industry Practice-I.
- TE Sem V: Soft Skill & Interpersonal Communication, Theory of Computer Science,
  Introduction to Intelligent System, Microprocessor, Professional Elective-I,
  Indian Constitution, Employability Skill Dev-III, Professional Skill-V, PBL-III.
- BE Sem VII: Data Warehousing & Mining, Cryptography & System Security, PE-II
  (DA/IS/CC), PE-III (ERP/IoT/Robo), OE-II (PDD/Japanese), Project.
  (BE timetables confirm these + labs + project blocks.)

### 1.8 Real rooms & faculty

- Rooms are numbered (SE COMP 606/608/609/607/718; TE 718/608/610; BE 532/513/610;
  FE 517/518/505/516/512 + lab rooms 006/519/315/324/325/304/305/306/326).
- Capacities are **not published** on the site (honest gap — must come from the college).
- Real COMP faculty (~39) with subject maps: e.g. CG→SuS/SR/MS, MP→TN/VN/RB,
  IIS→SPS/SB, TOC→VS/RS/GJ/SS, DBMS→HR/HP/LS/VK, DS→PP/FS/SM, UHV→AD/AR, IC→RE.
- Teachers teach **1–2 subjects** (plus filler duties), not 3–4.

---

## 2. What is wrong today (against this ground truth)

### 2.1 Seed (`scripts/seed_demo.py`)
| # | Problem | Ground truth |
|---|---|---|
| S1 | 5 fabricated departments (ELX/ELEC/CHEM/INST/CSBS); missing E&CS/CS&E/MME/IoT/CSE-IoT/ES&H | see §1.2 |
| S2 | FE lives under every engineering department | FE is ES&H-owned, one shared department |
| S3 | 4 divisions every year for every dept | BE often 3; smaller branches 1–2 |
| S4 | Invented FE scheme (Physics+BEE+PPS+Comm+Drawing all at once) | two real streams, Group I/Group 2 |
| S5 | Strength fixed at 60 | FE COMP 63; varies by intake; lateral-entry SE growth |
| S6 | 176 fabricated faculty/dept | COMP 39, IT 32–42, EXTC 23–29, HNS 77–88, … |
| S7 | Fabricated subject codes/streams; TE missing IP/PBL/DA; fillers treated as lectures | real subject lists §1.7; fillers are activities/online |
| S8 | Filler subjects (IC/SSIC/UHV/IKS/AAD/PS/…) not distinguishable, IC not online | online + notional + activity kinds needed |
| S9 | SE/TE grid 8×1h Mon–Sat, 08:30 start, lunch after slot 4, all years identical | 9-period 8:30–5:30, break T4, Sat=IP for SE/TE; FE totally different grid; BE no Sat |
| S10 | Rooms fabricated (`COMP-CR1..16`, `COMP-LAB1..10`, capacity 60/80) | real numbered rooms, capacity unpublished |
| S11 | No batches at all; practical = whole-division 2h block | 3 batches FE / 2 lab groups SE+ in parallel |

### 2.2 Engine (`app/engine/`)
| # | Problem | Fix |
|---|---|---|
| E1 | No batch layer / no parallel practical periods | new parallel-lab scheduling (§4) |
| E2 | No max-one-lab-per-day rule | new hard constraint |
| E3 | One time grid for all days | per-day `{day: slots[]}` grid |
| E4 | No online / notional / activity session kinds | session-kind field + online flag |
| E5 | No subject room affinity (bounces rooms) | room-affinity data + preference |
| E6 | Cross-dept shared subjects dropped unless a global flag is on | shared-subject tag + allow cross-dept teaching for them |
| E7 | No "teacher may teach N subjects / year restrictions" as data | extend TEACHER_YEAR_RESTRICTION + load caps |
| E8 | Conflict reservations only from PUBLISHED | extend to active (DRAFT/SELECTED/PUBLISHED) — DD-024 #5 |

### 2.3 Schema
| # | Problem | Fix |
|---|---|---|
| SC1 | `timetable_slots` has no batch identifier | add `batch_number` (int, null) |
| SC2 | No online / session-kind beyond SessionType enum | add `is_online` + `activity_type` (NOTIONAL/ACTIVITY) or extend SessionType |
| SC3 | `StudentGroup` has no parent-batch link for lab groups | nullable `parent_group_id` / `batch_order` on BATCH groups |
| SC4 | Subject has no shared/ES&H ownership marker | `department="Shared"`/`ES&H` convention (data, no column needed) or `is_shared` flag |
| SC5 | No real room numbers/capacities | seed data from §1.8 (capacity stays a college-data gap) |

### 2.4 Documentation (wrong info to fix)
| File | Wrong claim | Correction |
|---|---|---|
| `documentation/progress.md` | "real TCET L/T/P scheme", "12 departments, 16 classes each" | seed is a **fabricated demo**; real structure §1 |
| `documentation/plan.md` | "12/12 departments", framing as final | reframe as demo; real rollout is the task |
| `documentation/HANDOFF.md` | "TCET-style seed, 12 depts/16 classes", "176/dept" | reframe as demo; note fabricated depts |
| `documentation/timetable-generator-architecture.md` | "1976 faculty / 492 streams" as real | mark demo-only |
| `README.md` | already references `info/` — minor framing | ok, verify |

---

## 3. Fix plan (phased)

### Phase 0 — Documentation corrections (this pass)
Edit the four docs above to label the seed a **fabricated demo**, point to
`info/` + `sample/esah_fe_department_info.md` as the ground truth, and correct the
framing (not the numbers — the demo seed still has them until Phase 1 lands).
Add this plan to the doc index (`README.md` + `documentation/AGENTS.md`).

### Phase 1 — Real seed data (`scripts/seed_demo.py` rewrite)
1. **Departments** = the real 13 (§1.2), each with real faculty count; drop the 5
   fabricated ones. Add ES&H (HNS) as a department owning FE.
2. **FE model**:
   - FE divisions live under ES&H, named by intake (`COMP-A/B/C/D`, `MECH-A`, …),
     per-dept division count data-driven (COMP=4 default, configurable).
   - FE strengths = 63 (COMP); SE strengths bumped for lateral entry.
   - FE subjects = the real two streams; department tag = ES&H (or Shared).
   - FE profile grid = the FE grid (§1.5), Saturday online sessions included.
3. **Division structure** per branch per §1.4 (BE A–C etc.).
4. **Real schemes** per branch/semester §1.7 (start with COMP; others from
   `info/05-courses-and-results.md`).
5. **Faculty** = real names (from `info/04-faculty-directory.md` +
   `info/02-departments/*/faculty.md`), real initials mapping, 1–2 subject loads.
6. **Rooms** = real numbered rooms; capacities from the college (gap).
7. **Shared subjects** (IC, IKS, UHV, SSIC, Maths) tagged `department="Shared"` /
   `ES&H`; `allow_cross_dept_subjects` on; they can be taught by any dept's faculty.
8. **Grid params per profile** — SE/TE/BE/FE each get the correct grid; BE gets no
   Saturday; fillers (Notional/IP/PBL/PS/DA) represented with their session kind.
9. Auto-derive batches from strength: FE → 3, SE+ → 2 lab groups (4 batches D1–D4
   paired) — via `lab_batches` profile param (year-defaulted).

### Phase 2 — Engine: batch + parallel practicals
1. `SessionToSchedule` gains `batch_number` and a `parallel_key`; lab subjects with
   `weekly_hours` split into 2h blocks, each block becomes a **parallel group** of B
   sessions (one per batch), all sharing the same (day, slot), placed together.
2. Solver: for a parallel group, find (day, slot) + **B distinct** matching rooms; the
   whole division is occupied while any batch is in a lab; validate the group as a unit
   (pairwise faculty distinctness across batches too).
3. New hard rule **MAX_ONE_LAB_PER_DAY** (per group/batch) — enforced in placement and
   in post-commit honest counting.
4. Rotation falls out of first-fit + max-one-lab-per-day (different lab subjects land on
   different days).
5. `batch_number` written on each slot; exports/grid render `Batch B1` etc.

### Phase 3 — Engine: per-day grids + session kinds
1. Replace `_build_slot_times` with a per-day grid: profile param
   `day_grids = {day_of_week: [{start, end, break_after, duration}, ...]}` (or the
   current flat params still work as a default). FE/TE/BE each get their real grid.
2. Add `is_online` (no room) + `activity_type` (NOTIONAL/ACTIVITY) to slots/sessions;
   fillers become data (`Notional 08:00–11:15` merged block, PS-IV 6-batch, DA 3-batch,
   IP/PBL Saturday).
3. Room affinity: profile-level `room_affinity` (subject → preferred room) as a soft
   preference; default keep stable if the same room is available.
4. Active-timetable conflict reservations (DD-024 #5).

### Phase 4 — Data import tooling (optional but recommended)
A script (`scripts/import_tcet.py`) that reads `info/` (rosters, courses, grids,
faculty initials) and emits the seed rows, so re-imports track the site.

### Phase 5 — Re-baseline + verify
- Re-run `seed_demo --wipe`, `generate_college`, `full_stack_test.py`.
- Verify a generated COMP-TE-D against the real TE COMP-D grid cell-for-cell
  (subjects, batches, rooms, breaks, Saturday), and a generated COMP FE against the
  real FE grid.
- Confirm 0 violations, realistic contact hours (SE/TE ~42, BE ~38, FE ~31+).

---

## 4. Open items / gaps (need the college, not the website)
1. **Room capacities** — not published. Ask the college.
2. **Exact FE Sem I subject hours** for Group 2 (Chemistry stream) in odd sem, and the
   exact per-division FE division counts for every department this year.
3. AI&ML S.T. A–C timetable PDFs 404 on the site.
4. Full rosters for E&CS/MME (none published) and AI&DS/IoT/CSE-IoT (linked to COMP).
5. Which BCA/BBA/B.Voc/MCA/MBA timetables the product must generate (non-engineering).
6. Whether "notional learning" and "online lectures" should be generated or left as
   explicit free/blank blocks the admin fills.

## 5. Commit rule
Doc-only corrections (Phase 0) and this plan go in a doc commit. Code/seed/engine
changes (Phases 1–3) are separate commits, each with its own migration/test/doc sync,
per AGENTS.md. Record a DD-NNN in `documentation/design-decisions.md` when the seed is
rewritten (the fabricated departments are replaced by real ones).
