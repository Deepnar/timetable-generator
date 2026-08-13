# info/ — Machine-readable export format for the scraper

This file is a **spec for the scraping session** to follow so the timetable-api can
import TCET's data directly instead of hand-transcribing it. Today `info/` is prose +
tables; the app needs **JSON files** with the exact shapes below. Emit one JSON file per
entity under `info/import/` (alongside the existing markdown, which stays as the
human-readable source).

If you cannot produce every field, emit the file with the fields you can and leave the
rest `null` — do NOT invent values. Mark anything guessed with `"_note": "..."`.

The consuming importer is `scripts/import_tcet.py` (planned). It maps these files to the
app's schema: `timetable_profiles` / `profile_resources` / `subject_assignments` /
`timetable_slots` / `student_groups` / `faculty` / `subjects` / `rooms`.

---

## 0. File layout

```
info/import/
├── departments.json      # branches + ES&H, FE group, division counts, strengths
├── faculty.json          # every named faculty + the initials used in timetable grids
├── subjects.json         # per branch + semester: lecture/tutorial/lab/activity streams
├── rooms.json            # numbered venues from timetables (capacity if published)
├── groups.json           # every division (SE/TE/BE per branch + FE divisions under ES&H)
├── assignments.json      # who teaches which subject to which group (incl. per-batch)
├── grids.json            # per-year time grids: slots, breaks, Saturday
├── timetables.json       # the 55 division grids as data (ground truth for verification)
└── calendar.json         # academic calendar constraints (exam weeks, holidays, IP/PBL)
```

---

## 1. departments.json

```json
{
  "academic_year": "2026-27",
  "departments": [
    {
      "code": "COMP",
      "name": "Computer Engineering",
      "established": "AY 2002-03",
      "fe_group": "I",
      "fe_divisions": 4,
      "divisions": { "SE": 4, "TE": 4, "BE": 3 },
      "strength": { "FE": 63, "SE": 63, "TE": 70, "BE": 60 },
      "labs": 6,
      "classrooms": 5
    },
    {
      "code": "ES&H",
      "name": "Engineering Sciences & Humanities",
      "owns_fe": true,
      "labs": 18,
      "classrooms": 14
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `code` | branch code used everywhere (COMP, IT, EXTC, E&CS, MECH, CIVIL, CS&E, MME, AI&ML, AI&DS, IoT, CSE-IoT, ES&H) |
| `fe_group` | FE stream: `I` (Physics stream first — COMP, CSE-CS, CIVIL, CSE-IoT, AI&DS) or `II` (Chemistry stream first — IT, MECH, E&TC, E&CS, MME, AI&ML). If IoT is unassigned in the source, pick and flag `"_note"`. |
| `fe_divisions` | how many FE divisions this intake has (COMP = 4 this year, 3 last year — it changes) |
| `divisions` | SE/TE/BE division counts (BE often fewer than SE/TE) |
| `strength` | real strength per year if published (FE COMP = 63); else `null` |
| `labs` / `classrooms` | from the dept profile pages |

## 2. faculty.json

```json
{
  "faculty": [
    {
      "department_code": "COMP",
      "name": "Sushant Sawant",
      "initials": ["SuS", "SAS"],
      "designation": "Assistant Professor",
      "email": null,
      "max_hours_per_week": 20,
      "max_hours_per_day": 6
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `initials` | every abbreviation the timetable grids use for this person (resolved from `03-timetables/class/UG/FACULTY-INITIALS.md`). Include unresolved initials as separate rows with `"initials": ["VNS"], "name": null, "_note": "unresolved"` so the app can flag them. |
| `email` | only if published (rosters do not publish it; the app needs a unique login — the importer will synthesize `code.N@tcet.edu.in` when null). |

## 3. subjects.json

```json
{
  "subjects": [
    {
      "department_code": "COMP",
      "semester": 5,
      "name": "Computer Graphics",
      "code": "CG",
      "kind": "LECTURE",
      "hours_per_week": 3,
      "room_type": "CLASSROOM",
      "min_capacity": null,
      "is_online": false
    },
    {
      "department_code": "COMP",
      "semester": 5,
      "name": "Computer Graphics Lab",
      "code": "CG",
      "kind": "LAB",
      "hours_per_week": 2,
      "room_type": "LAB",
      "min_capacity": 40,
      "is_online": false
    },
    {
      "department_code": "COMP",
      "semester": 5,
      "name": "Indian Constitution",
      "code": "IC",
      "kind": "ACTIVITY",
      "hours_per_week": 1,
      "room_type": null,
      "is_online": true
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `kind` | `LECTURE` · `TUTORIAL` · `LAB` · `ACTIVITY` (fillers: PS, IP, PBL, DA, AAD, IKS, Notional) |
| `is_online` | lectures run online (IC in TE) get `true` and `room_type: null` |
| `department_code` | `ES&H` for FE subjects; for **shared subjects** (IC, IKS, UHV, SSIC, Maths) use `department_code: "SHARED"` |
| duplicate `code` with different `kind` | a subject split into L + T + P streams is one subject per stream, same code |

## 4. rooms.json

```json
{
  "rooms": [
    { "department_code": "COMP", "name": "606", "room_code": "606", "room_type": "CLASSROOM", "capacity": null, "building": null, "floor": null },
    { "department_code": "COMP", "name": "324", "room_code": "324", "room_type": "LAB", "capacity": null }
  ]
}
```

Use the **real venue numbers** from the division timetables (TE COMP: 718/608/610 +
labs 324/325/304/305/306/326; FE: 517/518/505/516/512 + labs 006/519/315). Capacities
are not published — leave `null` and add a `"_note"` so the app marks them as
college-data-gaps.

## 5. groups.json

```json
{
  "groups": [
    { "name": "COMP-SE-A", "department_code": "COMP", "year": 2, "semester": 3, "strength": 63, "type": "DIVISION" },
    { "name": "COMP-FE-A", "department_code": "ES&H", "year": 1, "semester": 1, "strength": 63, "type": "DIVISION", "_note": "FE divisions belong to ES&H, named by intake" }
  ]
}
```

Every division that appears in a timetable must be here. **FE divisions live under ES&H.**

## 6. assignments.json — who teaches what to whom (incl. batches)

```json
{
  "assignments": [
    { "subject_code": "CG", "subject_name": "Computer Graphics", "group_name": "COMP-TE-A", "faculty_name": "Sushant Sawant", "weekly_hours": 3, "batch_number": null },
    { "subject_code": "CG", "subject_name": "Computer Graphics Lab", "group_name": "COMP-TE-A", "faculty_name": "Sushant Sawant", "weekly_hours": 2, "batch_number": 1 },
    { "subject_code": "CG", "subject_name": "Computer Graphics Lab", "group_name": "COMP-TE-A", "faculty_name": "Pratiksha Deshmukh", "weekly_hours": 2, "batch_number": 2 }
  ]
}
```

| Field | Meaning |
|---|---|
| `batch_number` | **lab practicals run in parallel batches** (3 for FE, 2 lab groups for SE+). A lab subject has ONE assignment row **per batch**, each with its own faculty — this is exactly what the real grids show (`Lab CG D1 D2 SuS/PD` = CG lab, batches 1+2, faculty SuS + PD). `null` = whole-division lecture/tutorial/activity. |
| `weekly_hours` | per-batch contact hours (a 2h practical = 2 per batch row) |
| shared subjects | faculty may come from any department when the subject is `SHARED` |

## 7. grids.json — the time grids (they differ per year)

```json
{
  "grids": [
    {
      "department_code": "COMP",
      "year": 2,
      "working_days": [0, 1, 2, 3, 4, 5],
      "slots": [
        { "slot": 1, "start": "08:30", "end": "09:30" },
        { "slot": 2, "start": "09:30", "end": "10:30" },
        { "slot": 3, "start": "10:30", "end": "11:30" },
        { "slot": 4, "start": "11:30", "end": "12:30", "break": true }
      ],
      "breaks": [
        { "slot": 4, "label": "BREAK", "duration_minutes": 60 }
      ],
      "saturday": "IP / co-curricular / notional"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `year` | FE = 1, SE = 2, TE = 3, BE = 4 |
| `slots` | the full day (SE/TE = 9 × 1h 08:30–17:30; BE = 8, no Saturday; FE = 08:00 start, 15-min breaks, different lunch) |
| `break` | mark break slots; the app renders them as structural, not sessions |
| `saturday` | text describing the Saturday pattern (IP / co-curricular / none for BE / online IE-ISE for FE) |
| per-day grids | if a division's day differs (e.g. FE Monday lunch later), add `"day_overrides": {1: {"slots": [...]}}` |

## 8. timetables.json — the published division grids as data

The single most valuable file: the 55 (or as many as exist) division grids, one per
division, as **cell data** so the app can (a) verify a generated timetable cell-for-cell
and (b) load them as reference/seed input.

```json
{
  "timetables": [
    {
      "group_name": "COMP-TE-D",
      "academic_year": "2026-27",
      "semester": 6,
      "venue": "718/608/610",
      "effective_from": "06/07/2026",
      "class_incharge": "Ms. Soumyamol P.S.",
      "cells": [
        {
          "day": 0,
          "slot": 1,
          "kind": "NOTIONAL",
          "subject": null, "batch": null, "faculty": null, "room": null,
          "online": false, "label": "Notional Learning"
        },
        {
          "day": 0,
          "slot": 5,
          "kind": "LAB",
          "subject": "CG", "batch": [1, 2],
          "faculty": ["SuS", "PD"], "room": "324",
          "online": false, "label": "Lab CG D1 D2"
        },
        {
          "day": 2,
          "slot": 8,
          "kind": "ACTIVITY",
          "subject": "IC", "batch": null,
          "faculty": ["RE"], "room": null,
          "online": true, "label": "IC (online)"
        }
      ]
    }
  ]
}
```

| Cell field | Meaning |
|---|---|
| `day` | 0 = Monday … 6 = Sunday |
| `slot` | the slot number from the division's grid (grids.json) |
| `kind` | `LECTURE` · `TUTORIAL` · `LAB` · `ACTIVITY` · `NOTIONAL` · `EXAM` · `FREE` · `BREAK` |
| `batch` | batch(es) in this cell (`[1,2]` = D1D2; `[1,2,3]` = FE B1/B2/B3). A merged 2-period lab is ONE cell spanning 2 slots — keep the start slot and set `"span": 2` instead of duplicating rows. |
| `faculty` | faculty initials as in the grid (resolve via faculty.json) |
| `online` | online lecture |

**Parsing rules (from the founder + the existing pack):**
- A `NOTIONAL` block spanning e.g. 08:00–11:15 is **one cell** (`span`), not several.
- `LUNCH BREAK` / `SHORT BREAK` are structural cells, not subjects.
- A combined multi-period entry like `12:15–14:15 ELEC WS B1/B2 123/121` is one
  activity, two batches, two rooms → one cell with `"batch": [1,2]`,
  `"rooms": ["123","121"]`, `"span": 2`.
- Multiple parallel batches in one period = one cell per batch, same slot.

## 9. calendar.json — scheduling constraints

```json
{
  "academic_year": "2026-27",
  "odd_semester": { "start": "2026-06-08", "end": "2026-11-30" },
  "even_semester": { "start": "2027-01-02", "end": null },
  "holidays": ["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19"],
  "exam_windows": [
    { "label": "ISE-I", "start": "2026-07-13", "end": "2026-07-15" },
    { "label": "ISE-II", "start": "2026-08-22", "end": "2026-08-25" }
  ],
  "ip_pbl_dates": ["2026-08-08", "2026-08-22", "2026-09-12", "2026-09-26", "2026-10-03"],
  "events": { "zephyr": "2026-09-29 to 2026-10-01" },
  "rules": [
    "each faculty: min 42 lectures + 10 practical/tutorial sessions per semester",
    "ATKT window 3-14 Aug 2026"
  ]
}
```

Source: `info/01-institute/academic-calendar.md`.

---

## 10. What the app will do with each file

| File | Used for |
|---|---|
| `departments.json` | `timetable_profiles` (scope DEPT) + `student_groups` division counts |
| `faculty.json` | `faculty` rows + initials glossary |
| `subjects.json` | `subjects` rows (with `requirements_json` derived from kind/room_type) |
| `rooms.json` | `rooms` rows |
| `groups.json` | `student_groups` (FE divisions owned by ES&H) |
| `assignments.json` | `subject_assignments` incl. `batch_number` (drives parallel practicals) |
| `grids.json` | `profile_parameters` (slots/day, start, breaks, working days, per-day overrides) |
| `timetables.json` | reference ground truth for cell-for-cell verification + optional import |
| `calendar.json` | `HOLIDAY_CALENDAR` / `EXAM_DATE_SEPARATION` constraints |

## 11. Honest gaps to mark `null` (do not guess)

1. **Room capacities** — nowhere on the site. Leave `null` + `_note`.
2. **Division counts for non-COMP branches this year** — the site shows BE often 3,
   EXTC 2, etc. Emit exactly what the timetables show; the app default fills gaps.
3. **Unresolved faculty initials** (VNS, RK, …) — include as `name: null` rows so the
   app flags them for the college.
4. **Exact strengths** for SE/TE/BE — not published; only FE COMP = 63 is known.
5. **FE division counts per intake** — only COMP (4 this year, 3 last) is known.

If a file would be empty or fully guessed, **omit it** and note the omission here.
