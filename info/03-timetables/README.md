# Timetables — Everything Published on the TCET Website

This is the section the timetable-api project cares about most. Every timetable
artifact found on tcetmumbai.in is here, extracted to text.

## Class timetables (lecture timetables)

| Sub-section | Contents |
|---|---|
| `class/README.md` | **PG timetables** — ME-COMP SEM II (full grid + subject→faculty map), ME-IT SEM II (OCR), ME(PG) orientation schedule |
| `class/UG/README.md` | **UG division timetables** — index of all 55 divisions |
| `class/UG/<branch>/README.md` | per-branch division grids (subject + faculty initials + venues) |

**UG coverage by branch** (AY 2026-27 odd semester, W.E.F. 06/07/2026 unless noted):

| Branch | Divisions |
|---|---|
| Computer Engineering | SE A–D, TE A–D, BE A–C (12) + ME SEM I/II |
| Artificial Intelligence & ML | S.T. A–C, T.T., B.T. (5; ST A–C links are dead on site — TT/BT live) |
| Information Technology | ~10 divisions (from `IT time table.html`) |
| E&CS | SE Sem-III, TE Sem-V, BE Sem-VII |
| EXTC | SE-A/B, TE-A/B, BE-A/B |
| Civil | SE, TE, BE |
| Mechanical | SE, TE, BE |
| BCA | SY Sem-III, TY Sem-V (AY 2026-27) |
| MCA | SY Sem-III |
| MBA | Semester-III: Finance, Operations, HR, Marketing |
| H&W (HNS) | SIP Week 1/2/3 + Group 1/2 class timetables (FE induction) |

## Exam timetables

`exam/README.md` — every exam timetable PDF published on the exam-cell page
(2026 in-semester I/II, mid-term, supplementary July 2026 cycles, ISA ATKT 2026),
date-by-date rows per branch/year/semester.

## Note on formats

- Most UG timetables are official PDFs with a real text layer (extracted to
  `text/drive/`); a few are scans (OCR in `text/ocr/`).
- Grids use **faculty initials** (e.g. VK, RB, HR) — resolve names via
  `04-faculty-directory.md` and `02-departments/<branch>/faculty.md`.
- Venue numbers (e.g. 305, 606/609) are room numbers; capacities are not published.
