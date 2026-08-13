# Model Guide — How to Read This Pack

Give this file to any text-only model (or person) along with the `info/`
folder. It explains where everything is and how to interpret it.

## Orientation (read these first, in order)

1. **`README.md`** — master map: folder structure, coverage, honest gaps,
   and how the data maps to the timetable-api project.
2. **`01-institute/about.md`** — what TCET is (autonomy, accreditation, scale).
3. **`01-institute/leadership.md`** — who runs it (Chairman → Principal → Deans
   → HODs) and the official timetable approval chain.
4. **`01-institute/academic-calendar.md`** — the AY 2026-27 yearly schedule:
   90 teaching days, in-semester exam weeks, festival closures, ATKT window,
   even-semester start. **These are hard constraints for any scheduling task.**

## Where the different kinds of information live

| You want… | Go to |
|---|---|
| A branch's profile (vision, labs, classrooms, stats) | `02-departments/<branch>/README.md` |
| A branch's faculty roster | `02-departments/<branch>/faculty.md` |
| Every named person at TCET | `04-faculty-directory.md` |
| UG lecture timetables (per division, with grids) | `03-timetables/class/UG/<branch>/README.md` |
| PG lecture timetables (ME-COMP, ME-IT) | `03-timetables/class/README.md` |
| Exam timetables (2026 cycles) | `03-timetables/exam/README.md` |
| What subjects are taught per semester | `05-courses-and-results.md` |
| Syllabi / schemes | `02-departments/<branch>/syllabus.md` |
| Committees, NIRF, notices, reports | `01-institute/committees.md`, `06-notices-reports-nirf.md` |
| Raw page text (for anything not summarised) | `text/html/<page>.html.md` |

## How to read a division timetable (the format)

A division timetable file (e.g. `03-timetables/class/UG/computer-engineering/README.md`)
contains, per division:

- Header facts: `CLASS: S.E-A (SEM III)`, `Venue: 606/609`, `W.E.F: 06/07/2026`,
  `CLASS INCHARGE: <name>`.
- The grid: rows = days, columns = periods (8:30–5:30). Cells are written as
  `Subject Group-IDs Faculty-initials Room` — e.g. `Lab DBMS A1 A2 VK RB 305`
  means: DBMS lab, batch groups A1+A2, faculty VK and RB, room 305.
- **Faculty initials** (VK, RB, HR, …) are abbreviations — resolve them with
  **`03-timetables/class/UG/FACULTY-INITIALS.md`** (the glossary: initial →
  name → confidence) or the department roster in
  `02-departments/<branch>/faculty.md`.
- Some divisions (SE/TE COMP A/B, AI&ML TT/BT) have been **vision-verified**:
  their READMEs contain clean day×period tables plus the subject→faculty
  legend, transcribed from the official PDF images. Treat those tables as the
  authoritative reading over the flattened raw text.
- Load totals (e.g. "28 lectures × 15 weeks = 420h") and special blocks:
  BREAK, Notional Learning, Saturday = IP / co-curricular.
- Signature chain: class in-charge → HOD → Dean Academic → VP → Principal.

## Interpretation rules

- **OCR noise:** some grids come from scanned PDFs (tesseract OCR) — treat
  garbled cells as best-effort and cross-check with the raw file when a detail
  matters. Files from `text/drive/` (real text layer) are cleaner than
  `text/ocr/` files.
- **Dead links:** the AI&ML S.T.-A/B/C timetable PDFs 404 on the college site —
  only T.T. and B.T. exist.
- **Privacy:** result registers with student names/marks are intentionally NOT
  in this pack's documents. Only course structures are reproduced.
- **Recency:** the data reflects the website on 13 Aug 2026 (AY 2026-27 odd
  semester timetables, W.E.F. 06/07/2026).

## If the model needs to build a timetable model (the project's goal)

Use this data flow:
1. Resources: `02-departments/*/README.md` (labs, classrooms, faculty counts)
   + `04-faculty-directory.md` (people).
2. Teaching assignments: division grids (subject + faculty initials + groups)
   resolved against rosters → who teaches what, to which batch.
3. Slot structure: the 9-period 8:30–5:30 grid + break + Saturday pattern.
4. Constraints: `01-institute/academic-calendar.md` (exam weeks, holidays,
   festival closure, 42-lecture/10-practical minimum per faculty).
5. Exams: `03-timetables/exam/` as fixed external inputs.
