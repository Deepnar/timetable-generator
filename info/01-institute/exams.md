# TCET Examination Cell — Rules, Cycles, Notifications

Sources: `aboutexamsection.html`, `timetable.html`, `examnotification.html`,
`rules-for-progression.html`, `Semester End.html`, `result.html`, `convocation data.html`.

## Structure

- Examination Cell pages: About Examination Cell, Updated Convocation Data,
  Semester End, Rules for Progression, Notifications, Time Table, Results.
- Controller of Examination: Dr. Sanjeev Chaudhari.
- Board of Examination (BOE) is committee #23 in `committees.md`.

## Exam cycles (from timetable page, 2026)

| Cycle | Coverage | Artifact |
|---|---|---|
| IN SEMESTER EXAMINATION I – Sept 2026 | BCA / MCA | Drive PDF |
| IN SEMESTER EXAMINATION II – Sept 2026 | ALL BRANCHES | Drive PDF |
| MID TERM EXAMINATION – Sept 2026 | BBA / MBA (SY,TY) | Drive PDF |
| IN SEMESTER EXAMINATION I – Sept 2026 | ALL BRANCHES | Drive PDF |
| END (SUPPLEMENTARY) – July 2026 | MCA / BBA / BCA | Drive PDF |
| END SEMESTER (SUPPLEMENTARY) – July 2026 | ME / BVOC / BCA all branches | Drive PDF |
| END SEMESTER (SUPPLEMENTARY) – July 2026 | SE / TE / BE all branches | Drive PDF |
| END SEMESTER (SUPPLEMENTARY) (SEM IV) – July 2026 | BVOC all branches | Drive PDF |
| END SEMESTER (SUPPLEMENTARY) (SEM II) – July 2026 | FE.FT all branches | Drive PDF |
| END SEMESTER (SUPPLEMENTARY) (SEM II) – July 2026 | MBA | Drive PDF |
| IN SEMESTER EXAMINATION I – July 2026 | ALL BRANCHES | Drive PDF |

All artifacts downloaded into `info/raw/drive/` and text-extracted into
`info/text/drive/` — see `03-timetables/exam/` for the structured digest.

## Rules & related

- **Semester End** page: end-of-semester process (form `Semester End.html`)
- **Rules for Progression** (`rules-for-progression.html`): promotion criteria
  between semesters (ATKT-style rules)
- **Results** (`result.html`): result publication page; the full per-student
  office registers (mark sheets) are published as Drive PDFs — see
  `05-courses-and-results.md` (aggregated course data only; raw registers in
  `raw/drive/`)
- **Convocation data** (`convocation data.html`): convocation records
- **Notifications** (`examnotification.html`): exam-related notices

> **Project note:** exam timetables are published per-cycle PDFs on Google Drive;
> the API's exam-scheduling features should treat them as fixed external inputs,
> while `DRAFT → SELECTED → PUBLISHED` instances model the *class* timetable.
