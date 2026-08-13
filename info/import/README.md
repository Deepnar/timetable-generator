# info/import/ — machine-readable TCET data (JSON)

Generated **14 Aug 2026** from the vision-verified markdown pack
(`info/03-timetables/class/UG/` + `info/01-institute/`) by
`scripts/generate_tcet_import.py`. Consumed by `scripts/import_tcet.py`
(planned) to seed `timetable_profiles` / `profile_resources` /
`subject_assignments` / `timetable_slots` / `student_groups` / `faculty` /
`subjects` / `rooms`. Full field spec: `info/import-format.md`.

| File | Contents | Notes |
|---|---|---|
| `departments.json` | 16 departments (13 branches + BCA/MCA/MBA + ES&H) | `fe_group` I/II per esah doc; division counts from the published timetables |
| `faculty.json` | 126 rows: 68 resolved (name+initials) + 58 unresolved/ambiguous | unresolved initials `name: null` + `_note` so the app flags them; ambiguous rows carry `candidates` |
| `subjects.json` | 164 unique subject rows (dept × sem × code × kind) | LECTURE/TUTORIAL/LAB/ACTIVITY; hours/week null (derive from grids); MBA courses use name-as-code |
| `rooms.json` | 84 venue numbers from the division grids | capacities null (not published) |
| `groups.json` | 46 divisions (all 55 minus induction schedules/dead links) | FE divisions under ES&H; strengths null except where published |
| `assignments.json` | 118 rows: whole-division (batch null) + per-batch lab rows | faculty initials + resolved names where unambiguous; hours null |
| `grids.json` | 23 per-dept×year grids | SE/TE 9×1h 8:30–17:30 + Sat; BE 8 slots no Sat; EXTC 9:30 start; FE/ES&H |
| `timetables.json` | 46 division grids as cell data (491 KB) | day/slot/kind/subject/batch/faculty/room/online per cell; `label` = raw text |
| `calendar.json` | AY 2026-27 constraints | odd 08-06-2026, ISE-I/II windows, ATKT 3–14 Aug, Ganapati 15–19 Sep, Zephyr, IP/PBL dates |

## Regenerate

```bash
python3 scripts/generate_tcet_import.py   # rewrites info/import/*.json from the markdown pack
```

## Honest gaps (null on purpose, per spec §11)

- Room capacities, exact SE/TE/BE strengths, faculty emails — not published.
- Division counts for AI&DS/IoT/CSE-IoT/MME/CS&E/BBA/B.Voc — no timetables
  published (explicitly absent, see `03-timetables/class/UG/README.md`).
- AI&ML S.T. A–C — dead links on the site; only T.T. (sem 6) and B.T. (sem 8) exist.
- ES&H FE grid is the AY 2025-26 even semester (SEM II) — no AY 2026-27 odd FE
  timetable published yet.
- PG (ME) timetables are stale (2022/2024) — deliberately not imported.
