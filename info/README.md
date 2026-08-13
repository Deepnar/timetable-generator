# TCET — Complete Website Intelligence Pack

**Source:** https://www.tcetmumbai.in/ — crawled **13 Aug 2026**
**Volume:** 487 HTML pages · 112 site PDFs · 1,021 Google Drive PDFs · 168 OCR'd documents · all converted to text

This folder is the complete, structured dump of every piece of public information
about **Thakur College of Engineering & Technology (TCET), Mumbai** — read,
cleaned, and organised so a text-based AI (or a human) can navigate it without
re-visiting the website. It exists to feed the **timetable-api** project with
real TCET ground truth.

---

## 1. Folder map (read this first)

```
info/
├── README.md                          ← THIS FILE — master index & navigation map
│
├── 01-institute/                      ← College-level context (6 + 1 docs)
│   ├── about.md                       ← identity, autonomy, accreditations, ISO, awards
│   ├── academic-calendar.md           ← ★ AY 2026-27 odd-semester calendar (dates, rules)
│   ├── academics.md                   ← programs (21 UG / 11 PG / 5 PhD), OBE, admission
│   ├── committees.md                  ← all 27 committees with members
│   ├── exams.md                       ← exam cell, rules, cycles, notifications
│   ├── infrastructure.md              ← facilities, sports inventory, library, labs
│   └── leadership.md                  ← Chairman → Principal → Deans → HODs + approval chain
│
├── 02-departments/                    ← Per-branch folders (17), each with:
│   ├── README.md                      ← index table (established / faculty strength / labs)
│   └── <branch>/
│       ├── README.md                  ← profile: vision, mission, PSO, stats
│       ├── faculty.md                 ← ★ full faculty roster as published (name, DOJ, quals, experience, role)
│       ├── facilities.md              ← labs, classrooms, library, common facilities
│       ├── syllabus.md                ← scheme/syllabus pages & PDFs
│       └── activities.md              ← clubs, chapters, publications, events
│
├── 03-timetables/                     ← ★ THE TIMETABLE SECTION (heart of the project)
│   ├── class/
│   │   ├── README.md                  ← PG class timetables (ME-COMP, ME-IT) extracted w/ faculty maps
│   │   └── UG/                        ← ★ UG division timetables, per branch
│   │       ├── README.md              ← index of all 55 divisions (venue, W.E.F., class in-charge)
│   │       └── <branch>/README.md     ← each division's grid text
│   └── exam/README.md                 ← all exam timetables (2026 cycles) extracted
│
├── 04-faculty-directory.md            ← ★ master list: ~200 faculty across all depts + leadership
├── 05-courses-and-results.md          ← ★ course lists per semester/branch from 560 result registers
├── 06-notices-reports-nirf.md         ← notices, IQAC/NAAC docs, NIP reports, NIRF data index
├── 07-blog-articles.md                ← index of 51 marketing/blog pages (one-line summaries)
├── 08-misc-pages.md                   ← index of remaining institute pages
│
├── raw/                               ← untouched downloads (backup / re-check)
│   ├── html/    (487 pages)
│   ├── pdf/     (112 site PDFs)
│   ├── drive/   (1,021 Google Drive PDFs — results, timetables, syllabi, reports)
│   └── flipbook-anfd-calendar.png     ← institute academic calendar image
│
└── text/                              ← extracted text, one file per raw file
    ├── html/    (487 .md conversions)
    ├── pdf/     (112 .txt)
    ├── drive/   (1,021 .txt)
    └── ocr/     (168 .ocr.txt — OCR of image-only PDFs)
```

## 2. Reading order (for the model)

1. `01-institute/about.md` + `leadership.md` — who TCET is, who runs it.
2. `01-institute/academic-calendar.md` — the master yearly schedule (constraints).
3. `02-departments/README.md` + each branch's `README.md` — the resource universe
   (branches, faculty strength, labs, classrooms).
4. `03-timetables/` — all published timetables: UG divisions, PG, exam cycles.
5. `04-faculty-directory.md` — the people.
6. `05-courses-and-results.md` — what is taught per semester.
7. `06/07/08` — accreditation, reports, notices, blogs (context, not constraints).

## 3. Coverage & honest gaps

| Topic | Status | Where |
|---|---|---|
| Institute facts, autonomy, accreditation | ✅ | `01-institute/about.md` |
| Leadership + approval chain | ✅ | `01-institute/leadership.md` |
| Committees (27) with members | ✅ | `01-institute/committees.md` |
| Academic calendar AY 2026-27 | ✅ | `01-institute/academic-calendar.md` |
| Programs & education model | ✅ | `01-institute/academics.md` |
| Exam cell rules & cycles | ✅ | `01-institute/exams.md` |
| Facilities / sports / library | ✅ | `01-institute/infrastructure.md` |
| Per-dept profile (labs, rooms, strength) | ✅ 17 branches | `02-departments/` |
| **Faculty rosters** | ✅ 7 depts full (COMP 65, H&W 88, IT 42, EXTC 29, MECH 10, CIVIL 7, AI&ML 8) | `02-departments/*/faculty.md`, `04-faculty-directory.md` |
| **UG class timetables** | ✅ 55 divisions (COMP SE/TE/BE A–D, AI&ML, E&CS, EXTC, CIVIL, MECH, IT, BCA, MCA, MBA + HNS SIP) | `03-timetables/class/UG/` |
| PG class timetables | ✅ ME-COMP, ME-IT (faculty-subject maps) | `03-timetables/class/README.md` |
| Exam timetables | ✅ 2026 cycles (11 official PDFs + ISA ATKT) | `03-timetables/exam/` |
| Courses per semester | ✅ from 560 result registers | `05-courses-and-results.md` |
| Syllabi / schemes | ⚠️ ME syllabi + per-dept syllabus pages exist; full UG syllabus PDFs are scattered | `02-departments/*/syllabus.md` |
| NIRF data | ⚠️ submission forms + report scans (2016–2026); rank numbers are inside image PDFs | `06-notices-reports-nirf.md` |

**Still NOT published anywhere on the site** (must be obtained from the college):
1. Room capacities (only room numbers appear in timetables, e.g. 305, 606/609).
2. Faculty workload / total-teaching-load sheets (only per-class timetables with
   faculty initials exist — the initials are resolvable via rosters).
3. MBA/BBA/B.Voc/MME/E&CS full rosters (E&CS & MME have no roster page; MBA/BBA/B.Voc none).
4. AI&DS / IoT / CSE-IoT rosters (site links the COMP roster as fallback).

## 4. Timetable artifacts — quick index

| Type | What | Location |
|---|---|---|
| UG class timetables (AY 2026-27 odd sem, W.E.F. 06/07/2026) | SE/TE/BE COMP A–D (12), AI&ML ST-A/B/C, TT, BT, E&CS SE/TE/BE, EXTC SE-A/B, TE-A/B, BE-A/B, CIVIL SE/TE/BE, MECH, IT (10), BCA SY/TY, MCA SY, MBA FIN/OP/HR/MKT | `03-timetables/class/UG/` |
| HNS / SIP induction timetables | SIP Week 1/2/3 + Group 1/2 class timetables (FE) | `03-timetables/class/UG/humanities-sciences/` |
| PG class timetables | ME-COMP SEM II (subject→faculty map), ME-IT SEM II | `03-timetables/class/README.md` |
| Exam timetables 2026 | In-sem I/II, mid-term, supplementary (July 2026), ISA ATKT | `03-timetables/exam/README.md` |

**Timetable format (typical division):** form `TCET/<DEPT>/FRM/IP-02/06-(Class)`,
8:30–5:30 grid, subject + faculty-initial pairs (e.g. `Lab DBMS A1 A2 VK RB 305`),
venue numbers, break/notional-learning blocks, Saturday = IP / co-curricular,
load totals (e.g. 28 lectures × 15 weeks = 420h + 240 indirect + 60 internship =
720h/sem), signature chain (class in-charge → HOD → Dean Academic → VP → Principal).

## 5. How this feeds the timetable-api

| API concept | Source data |
|---|---|
| `profile_resources` (faculty/rooms/groups/subjects) | `02-departments/*/README.md` (labs, classrooms, faculty strength), `04-faculty-directory.md` |
| `subject_assignments` (who teaches what, whom) | division timetables' subject+faculty-initial grid (`03-timetables/class/UG/`) resolved against rosters |
| Slot structure | timetable grids: 8:30–5:30, 9 periods, break, zero hour, Saturday IP |
| Constraints (holidays, exam weeks) | `01-institute/academic-calendar.md` |
| Exam scheduling | `03-timetables/exam/` |
| DRAFT→SELECTED→PUBLISHED workflow | leadership approval chain in `01-institute/leadership.md` |
| Course catalog per semester | `05-courses-and-results.md` |

## 6. How it was built (reproducibility)

Wave 1: sitemap + homepage crawl → 258 pages, 90 PDFs, 779 drive files.
Wave 2: department JS-menu files (homecmpn.html, IThome.html, EXTCMenu.html, …)
revealed hidden subpages → +229 pages (faculty, timetables, syllabi, calendars).
Wave 3: re-scan of all pages → +1,021 drive PDFs total.
All HTML → markdown (tables preserved); PDFs → pdftotext; image-only PDFs → OCR
(tesseract). Crawl scripts were one-off tools in /tmp (not part of the repo).
