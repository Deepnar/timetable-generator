"""Import the machine-readable TCET data (``info/import/*.json``) into Postgres.

Consumes the JSON emitted by ``scripts/generate_tcet_import.py`` (spec:
``info/import-format.md``) and seeds the real college structure:

- real departments (incl. ES&H owning FE), divisions from the published grids,
- real faculty (resolved names only; unresolved initials are logged + skipped),
- real subjects per branch+semester (hours derived from the published grids),
- real numbered rooms,
- per-division profiles with the real per-year time grid + constraints,
- ``subject_assignments`` with per-batch rows for parallel lab practicals.

Usage:
    uv run python -m scripts.import_tcet [--wipe]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from sqlalchemy import select, func

from app.database import SessionLocal
from app.models.faculty import Faculty
from app.models.groups import StudentGroup, GroupType
from app.models.rooms import Room, RoomType
from app.models.subjects import Subject
from app.models.subject_assignments import SubjectAssignment
from app.models.profiles import (
    TimetableProfile, ProfileResource, ProfileParameter, ResourceType,
    ScopeType, ParamType,
)
from app.models import HardConstraint, SoftConstraint

HERE = os.path.dirname(os.path.abspath(__file__))
IMPORT_DIR = os.path.join(os.path.dirname(HERE), "info", "import")

# Only import the branches with real published-grid knowledge. MBA/MCA/BCA,
# AI&ML, AI&DS, IoT, CSE-IoT, CS&E, MME and the FE group either publish no
# grids or their grids carry no resolvable subject/faculty data — leave them
# out until the college supplies real data.
# Phase 0-5 scope (D5): COMP only — 11 divisions with a real roster exercise
# every hard case; the other branches are shape-only synthetic and make bugs
# unattributable. Re-admit IT at Phase 5, the rest after.
REAL_DATA_CODES = {"COMP"}

KIND_SESSION = {
    "LECTURE": "LECTURE",
    "TUTORIAL": "TUTORIAL",
    "LAB": "LAB",
    "ACTIVITY": "ACTIVITY",
}

_FIRST = ["Aarav", "Priya", "Rohan", "Sneha", "Kiran", "Meera", "Aditya",
          "Ananya", "Vikram", "Kavita", "Nikhil", "Pooja", "Rahul", "Shreya",
          "Sandeep", "Neha", "Amit", "Ritu", "Gaurav", "Divya", "Om", "Ishaan",
          "Tanvi", "Sahil", "Riya", "Arjun", "Karan", "Nisha", "Dev", "Sana"]
_LAST = ["Patel", "Sharma", "Iyer", "Kulkarni", "Desai", "Joshi", "Rao",
         "Nair", "Gupta", "Mehta", "Singh", "Reddy", "Bhat", "Fernandes",
         "Chauhan", "Naik", "Pillai", "Hegde", "Thakur", "More", "Kadam",
         "Pawar", "Sawant", "Gavde", "Salunkhe", "Tiwari", "Verma", "Das"]


def _load(name: str) -> dict:
    with open(os.path.join(IMPORT_DIR, name)) as f:
        return json.load(f)


def _session_type(kind: str):
    from app.models.generation import SessionType
    return SessionType(KIND_SESSION.get(kind, "CUSTOM"))


def _requirements(kind: str, room_type, is_online: bool) -> dict | None:
    """Map an import subject row to the app's ``requirements_json`` spec."""
    if kind == "LAB":
        return {"session_type": "LAB", "room_types": ["LAB"], "min_capacity": 40}
    if is_online:
        return {"session_type": KIND_SESSION.get(kind, "CUSTOM"), "room_types": []}
    if room_type == "LAB":
        return {"session_type": "LAB", "room_types": ["LAB"]}
    return {"session_type": KIND_SESSION.get(kind, "CUSTOM"), "room_types": ["CLASSROOM"]}


def _scheme_hours(kind: str) -> int:
    """Real weekly hours per stream kind: ~3 lectures, 1 tutorial, 2h lab, 2h activity.

    The grid cell-count derivation is noisy (it over-requests the week — e.g.
    a class ends up asking for 88 sessions in a 54-slot week). The published
    scheme is the truth: a lecture subject runs 3×/week, a tutorial 1×, a
    practical 2h once a week per batch.
    """
    return {"LAB": 2, "TUTORIAL": 1, "ACTIVITY": 2}.get(kind, 3)


def _derive_hours(timetables: list) -> tuple[dict, dict]:
    """weekly hours from the published grids.

    Returns:
      subject_hours: {(dept, sem, code, kind): int} — max load seen anywhere.
      group_hours:   {(group, code, kind): int} — that division's weekly load.
    LAB cells count as a 2h block (real practicals); a division's per-batch lab
    hours are always 2 (each batch does the lab once a week).
    """
    subject_hours: dict = {}
    group_hours: dict = {}
    for tt in timetables:
        gname = tt["group_name"]
        dept = gname.split("-")[0]
        sem = tt["semester"]
        per_group: dict = {}
        for c in tt["cells"]:
            code = c.get("subject")
            kind = c.get("kind")
            if not code or kind in ("NOTIONAL", "BREAK", "FREE", None):
                continue
            hours = 2 if kind == "LAB" else 1
            per_group[(code, kind)] = per_group.get((code, kind), 0) + hours
        for (code, kind), hrs in per_group.items():
            group_hours[(gname, code, kind)] = hrs
            if kind == "LAB":
                hrs = 2
            key = (dept, sem, code, kind)
            subject_hours[key] = max(subject_hours.get(key, 0), hrs)
    return subject_hours, group_hours


def wipe(db) -> None:
    from sqlalchemy import text
    tables = [
        "timetable_slots", "timetable_instances", "timetable_generations",
        "timetable_overrides", "timetable_history", "timetable_reset_log",
        "profile_combination_members", "profile_combinations",
        "profile_parameters", "profile_resources", "timetable_profiles",
        "subject_assignments", "hard_constraints", "soft_constraints",
        "faculty_availability", "room_blackouts",
        "student_groups", "subjects", "faculty", "rooms", "audit_logs",
    ]
    with db.begin():
        for t in tables:
            db.execute(text(f"TRUNCATE {t} RESTART IDENTITY CASCADE"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wipe", action="store_true",
                        help="truncate all scheduling tables before importing")
    args = parser.parse_args()

    departments = _load("departments.json")["departments"]
    faculty_rows = _load("faculty.json")["faculty"]
    subjects_rows = _load("subjects.json")["subjects"]
    rooms_rows = _load("rooms.json")["rooms"]
    groups_rows = _load("groups.json")["groups"]
    assignments_rows = _load("assignments.json")["assignments"]
    grids_rows = _load("grids.json")["grids"]
    timetables = _load("timetables.json")["timetables"]
    calendar = _load("calendar.json")

    subject_hours, group_hours = _derive_hours(timetables)

    # Scope to the branches with real data.
    timetables = [t for t in timetables
                  if t["group_name"].split("-")[0] in REAL_DATA_CODES]
    groups_rows = [g for g in groups_rows if g["department_code"] in REAL_DATA_CODES]
    subjects_rows = [s for s in subjects_rows if s["department_code"] in REAL_DATA_CODES]
    assignments_rows = [a for a in assignments_rows
                        if a["group_name"].split("-")[0] in REAL_DATA_CODES]
    rooms_rows = [r for r in rooms_rows if r.get("department_code") in REAL_DATA_CODES]

    db = SessionLocal()
    try:
        if args.wipe:
            print("wiping scheduling tables…")
            wipe(db)

        from app.models.admin import Admin
        admin = db.query(Admin).first()
        if admin is None:
            from app.utils.auth import hash_password
            admin = Admin(email="seed@example.com", name="Seed Admin",
                          password=hash_password("seed123"))
            db.add(admin)
            db.flush()

        dept_by_code = {d["code"]: d for d in departments}
        term_start = (calendar.get("odd_semester") or {}).get("start") or "2026-06-08"

        # ── faculty ───────────────────────────────────────────
        # Resolved rows carry a single name; ambiguous rows carry a `candidates`
        # list of the real roster names sharing an initial. Every candidate is a
        # real published faculty member, so create a row per unique name — the
        # pools stay full and assignments resolve by department context. Truly
        # unresolved initials (name null AND no candidates) get a **synthetic**
        # faculty member so no teaching slot is silently dropped — the site only
        # shows the initials, so the college's shape is preserved with a
        # placeholder the admin can rename.
        initials_to_names: dict[str, list[str]] = {}
        faculty_by_name: dict[str, Faculty] = {}
        faculty_by_initial: dict[str, Faculty] = {}
        email_counter = 0
        synth_count = 0

        def _mk_faculty(nm: str, dept_code) -> Faculty:
            nonlocal email_counter
            email_counter += 1
            local = (dept_code or "tcet").lower().replace("&", "").replace("(", "").replace(")", "")
            dept_name = dept_by_code.get(dept_code, {}).get("name") if dept_code else None
            fac = Faculty(name=nm, email=f"{local}.{email_counter}@tcet.edu.in",
                          department=dept_name or "Faculty",
                          max_hours_per_week=30, max_hours_per_day=8)
            db.add(fac)
            db.flush()
            return fac

        def _synth_name(ini: str) -> str:
            rng = __import__("random").Random(hash(ini) & 0xFFFF)
            first = rng.choice(_FIRST)
            last = rng.choice(_LAST)
            return f"{first} {last}"

        for row in faculty_rows:
            names = []
            if row.get("name"):
                names = [row["name"]]
            elif row.get("candidates"):
                names = [c.strip() for c in str(row["candidates"]).split(";") if c.strip()]
            if not names:
                # unresolved initial with no candidate — synthesize one member
                for ini in row.get("initials") or []:
                    nm = _synth_name(ini)
                    base = nm
                    n = 1
                    while nm in faculty_by_name:
                        nm = f"{base} {n}"
                        n += 1
                    fac = _mk_faculty(nm, row.get("department_code"))
                    fac.department = "Faculty"
                    faculty_by_name[nm] = fac
                    faculty_by_initial[ini] = fac
                    initials_to_names.setdefault(ini, []).append(nm)
                    synth_count += 1
                continue
            for ini in row.get("initials") or []:
                initials_to_names.setdefault(ini, [])
                for nm in names:
                    if nm not in initials_to_names[ini]:
                        initials_to_names[ini].append(nm)
            for nm in names:
                if nm in faculty_by_name:
                    continue
                faculty_by_name[nm] = _mk_faculty(nm, row.get("department_code"))
        # Dedicated per-branch faculty pools (info/import/synthetic_branches.json):
        # every branch gets ~40 branch-bound teachers (COMP uses the real roster;
        # the rest are synthesized at the same scale). A teacher belongs to ONE
        # branch and never teaches in another.
        synthetic = json.load(open(os.path.join(IMPORT_DIR, "synthetic_branches.json")))
        for row in synthetic.get("faculty", []):
            nm = row["name"]
            if nm in faculty_by_name:
                continue
            fac = _mk_faculty(nm, row["department_code"])
            fac.department = dept_by_code.get(row["department_code"], {}).get("name", "Faculty")
            faculty_by_name[nm] = fac
        db.flush()
        print(f"  faculty: {len(faculty_by_name)} created "
              f"({synth_count} synthetic for unresolved initials)")

        # ── rooms ─────────────────────────────────────────────
        # Room *type* is not in the source, so derive it from usage in the
        # published grids: a room that hosts a LAB cell is a lab.
        lab_room_names: set[str] = set()
        for tt in timetables:
            for c in tt.get("cells", []):
                if c.get("kind") == "LAB" and c.get("room"):
                    lab_room_names.update(
                        p.strip() for p in str(c["room"]).split("/") if p.strip())
        rooms_by_code: dict[str, Room] = {}
        rooms_by_dept: dict[str, list[Room]] = {c: [] for c in REAL_DATA_CODES}
        for row in rooms_rows:
            is_lab = row["name"] in lab_room_names
            rtype = RoomType.LAB if is_lab else RoomType.CLASSROOM
            cap = row.get("capacity") or (60 if rtype == RoomType.LAB else 80)
            r = Room(name=row["name"], room_code=row.get("room_code") or row["name"],
                     room_type=rtype, capacity=cap,
                     building="Main", floor=1, has_projector=True, has_ac=True)
            db.add(r)
            rooms_by_code[row["name"]] = r
            dept = row.get("department_code")
            if dept in rooms_by_dept:
                rooms_by_dept[dept].append(r)
        # Per-branch synthetic rooms: 16 classrooms (floors 1/5/6/7) + 8 labs
        # (floor 3), sized like the real college (see build_synthetic_branches.py).
        for row in synthetic.get("rooms", []):
            dept = row["department_code"]
            if dept not in rooms_by_dept:
                continue
            if row["name"] in rooms_by_code:
                continue
            rtype = RoomType.LAB if row.get("room_type") == "LAB" else RoomType.CLASSROOM
            r = Room(name=row["name"], room_code=row["name"], room_type=rtype,
                     capacity=row.get("capacity") or (45 if rtype == RoomType.LAB else 80),
                     building="Main", floor=row.get("floor", 1),
                     has_projector=(rtype != RoomType.LAB), has_ac=True)
            db.add(r)
            rooms_by_code[row["name"]] = r
            rooms_by_dept[dept].append(r)
        db.flush()

        # ── subjects ──────────────────────────────────────────
        subjects_by_key: dict = {}
        skipped_subjects = 0
        used_codes: set[str] = set()
        for idx, row in enumerate(subjects_rows):
            key = (row["department_code"], row["semester"], row["code"], row["kind"])
            dept_name = dept_by_code.get(row["department_code"], {}).get("name", "Shared")
            hrs = _scheme_hours(row["kind"])
            base = (
                f"{row['department_code'].replace('&', '').replace('-', '')[:4]}"
                f"-S{row['semester']}-"
                f"{re.sub(r'[^A-Za-z0-9]', '', row['code'])[:8]}-"
                f"{row['kind'][:1]}"
            )
            code = base[:19]
            n = 1
            while code in used_codes:
                code = f"{base[:16]}-{n}"
                n += 1
            used_codes.add(code)
            s = Subject(
                name=row["name"][:95],
                subject_code=code,
                department=dept_name, semester=row["semester"],
                hours_per_week=hrs,
                requires_lab=(row["kind"] == "LAB"),
                requirements_json=_requirements(row["kind"], row.get("room_type"),
                                                row.get("is_online", False)),
            )
            db.add(s)
            subjects_by_key[key] = s
        db.flush()

        # ── groups + profiles ─────────────────────────────────
        grid_by_dept_year = {(g["department_code"], g["year"]): g for g in grids_rows}

        # Per-division data from the published timetable (the ground truth):
        #  - preferred_rooms: the real venue + cell rooms, so generation reuses
        #    the college's actual rooms;
        #  - home_rooms: the venue rooms (primary + secondary) for the home-room
        #    hard restriction (A5);
        #  - break_slots: the numbered BREAK row of that division's grid (A2);
        #  - working_days: the days that actually carry teaching cells (A2);
        #  - saturday_policy: NONE unless the grid teaches on Saturday.
        _TEACHING_KINDS = ("LECTURE", "TUTORIAL", "LAB", "ACTIVITY")
        preferred_by_group: dict[str, list[int]] = {}
        home_rooms_by_group: dict[str, list[int]] = {}
        break_slots_by_group: dict[str, list[int]] = {}
        working_days_by_group: dict[str, list[int]] = {}
        saturday_policy_by_group: dict[str, str] = {}
        for tt in timetables:
            gname = tt["group_name"]
            names = set()
            venue = tt.get("venue")
            venue_ids: list[int] = []
            if venue:
                names.update(v.strip() for v in venue.split("/") if v.strip())
                for v in (v.strip() for v in venue.split("/") if v.strip()):
                    if v in rooms_by_code and v not in venue_ids:
                        venue_ids.append(rooms_by_code[v].id)
            for c in tt.get("cells", []):
                r = c.get("room")
                if r:
                    names.update(p.strip() for p in str(r).split("/") if p.strip())
            preferred_by_group[gname] = [
                rooms_by_code[n].id for n in names if n in rooms_by_code
            ]
            home_rooms_by_group[gname] = venue_ids

            breaks = sorted({c["slot"] for c in tt.get("cells", [])
                             if c.get("kind") == "BREAK" and c.get("slot")})
            # The break position varies per day in the real grids (a college
            # that cannot seat everyone at once staggers lunch), and the raw
            # scrape carries noise. A division declares ONE dominant break row
            # (the modal slot across teaching days) — the audit measured the
            # real BREAK row at slot 4×45, 5×51, 3×41, 6×28. Ties pick the
            # earliest slot.
            from collections import Counter
            break_counts = Counter(
                c["slot"] for c in tt.get("cells", [])
                if c.get("kind") == "BREAK" and c.get("slot") is not None)
            if break_counts:
                dominant = min(
                    (s for s, _ in break_counts.most_common()),
                    key=lambda s: (-break_counts[s], s))
                break_slots_by_group[gname] = [dominant]
            else:
                break_slots_by_group[gname] = []

            teaching_days = sorted({c["day"] for c in tt.get("cells", [])
                                    if c.get("kind") in _TEACHING_KINDS
                                    and c.get("day") is not None})
            working_days_by_group[gname] = teaching_days
            # Saturday policy from what Saturday actually carries: real
            # teaching -> FULL, activity/IP only -> ACTIVITY_ONLY, nothing ->
            # NONE (COMP/IT/EXTC teach no Saturday classes).
            saturday_teaching = {c["day"] for c in tt.get("cells", [])
                                 if c.get("kind") in ("LECTURE", "TUTORIAL", "LAB")
                                 and c.get("day") == 5}
            saturday_activity = {c["day"] for c in tt.get("cells", [])
                                 if c.get("kind") == "ACTIVITY"
                                 and c.get("day") == 5}
            if saturday_teaching:
                saturday_policy_by_group[gname] = "FULL"
            elif saturday_activity:
                saturday_policy_by_group[gname] = "ACTIVITY_ONLY"
            else:
                saturday_policy_by_group[gname] = "NONE"

        group_rows = []
        for row in groups_rows:
            name = row["name"]
            dept_code = row["department_code"]
            dept_name = dept_by_code.get(dept_code, {}).get("name", dept_code)
            strength = row.get("strength")
            if strength is None:
                # Not published; synthesize the realistic shape (lateral-entry
                # SE matches FE, TE is the largest cohort).
                strength = {1: 63, 2: 63, 3: 70, 4: 60}.get(row["year"], 60)
            home_ids = home_rooms_by_group.get(name, [])
            g = StudentGroup(name=name, group_type=GroupType.DIVISION,
                             department=dept_name, year=row["year"],
                             semester=row["semester"], strength=strength,
                             home_room_id=home_ids[0] if home_ids else None,
                             home_room_secondary_id=home_ids[1] if len(home_ids) > 1 else None)
            db.add(g)
            db.flush()
            group_rows.append((name, g, dept_code))

            grid = grid_by_dept_year.get((dept_code, row["year"]))
            _make_profile(
                db, admin, f"{dept_name} — {name}", row["semester"], dept_name,
                list(rooms_by_code.values()), list(faculty_by_name.values()),
                [g], grid, term_start, row["year"],
                preferred_rooms=preferred_by_group.get(name, []),
                break_slots=break_slots_by_group.get(name, []),
                working_days=working_days_by_group.get(name),
                saturday_policy=saturday_policy_by_group.get(name, "NONE"),
            )
        db.flush()
        group_by_name = {n: (g, d) for n, g, d in group_rows}

        # ── synthesize LAB subjects referenced by batched assignments ──
        # The published grids carry labs as cells of a subject code (e.g. "CG")
        # with batch ids, not as separate legend entries — so a LAB subject row
        # often does not exist yet. Create one per (dept, sem, code) so the
        # parallel-practical engine has a real LAB subject to schedule.
        lab_extra: dict = {}
        for row in assignments_rows:
            if not row.get("batch_number"):
                continue
            ginfo = group_by_name.get(row["group_name"])
            if not ginfo:
                continue
            g, dept_code = ginfo
            key = (dept_code, g.semester, row["subject_code"], "LAB")
            if key in subjects_by_key or key in lab_extra:
                continue
            base = subjects_by_key.get(
                (dept_code, g.semester, row["subject_code"], "LECTURE"))
            name = (base.name if base else row["subject_code"]) + " Lab"
            dept_name = dept_by_code.get(dept_code, {}).get("name", "Shared")
            code = f"{dept_code.replace('&','').replace('-','')[:4]}-S{g.semester}-{re.sub(r'[^A-Za-z0-9]','',row['subject_code'])[:8]}-Lb"
            n = 1
            while code in used_codes:
                code = f"{code[:16]}-{n}"
                n += 1
            used_codes.add(code)
            s = Subject(name=name, subject_code=code, department=dept_name,
                        semester=g.semester, hours_per_week=2, requires_lab=True,
                        requirements_json={"session_type": "LAB",
                                           "room_types": ["LAB"], "min_capacity": 40})
            db.add(s)
            lab_extra[key] = s
        db.flush()
        subjects_by_key.update(lab_extra)

        # ── assignments (resolve faculty + hours) ─────────────
        created = skipped = 0
        seen_assignments: set[tuple] = set()
        for row in assignments_rows:
            ginfo = group_by_name.get(row["group_name"])
            if not ginfo:
                skipped += 1
                continue
            g, dept_code = ginfo
            key = (dept_code, g.semester, row["subject_code"], "LAB" if row.get("batch_number") else "LECTURE")
            subject = subjects_by_key.get(key)
            if subject is None:
                # try all kinds for the code
                for k in ("LECTURE", "TUTORIAL", "ACTIVITY", "LAB"):
                    subject = subjects_by_key.get((dept_code, g.semester, row["subject_code"], k))
                    if subject:
                        break
            if subject is None:
                skipped += 1
                continue
            faculty = None
            if row.get("faculty_name"):
                faculty = faculty_by_name.get(row["faculty_name"])
            if faculty is None and row.get("faculty_initials"):
                # The glossary often lists several people under one initial
                # (e.g. SS -> 3 names). Pick the candidate whose department
                # matches the class being scheduled; fall back to the first.
                candidates = initials_to_names.get(row["faculty_initials"], [])
                for nm in candidates:
                    cand = faculty_by_name.get(nm)
                    if cand and (cand.department in (None, "Faculty")
                                 or cand.department == g.department):
                        faculty = cand
                        break
                if faculty is None and candidates:
                    faculty = faculty_by_name.get(candidates[0])
            if faculty is None and row.get("faculty_initials"):
                faculty = faculty_by_initial.get(row["faculty_initials"])
            if faculty is None and row.get("faculty_initials"):
                # Any remaining initial (present in a grid but never in the
                # glossary) gets a synthetic faculty member on the spot.
                ini = row["faculty_initials"]
                nm = _synth_name(ini)
                base = nm
                n = 1
                while nm in faculty_by_name:
                    nm = f"{base} {n}"
                    n += 1
                fac = _mk_faculty(nm, dept_code)
                fac.department = g.department
                faculty_by_name[nm] = fac
                faculty_by_initial[ini] = fac
                faculty = fac
                synth_count += 1
            if faculty is None:
                skipped += 1
                continue
            if faculty.department is None or faculty.department == "Faculty":
                faculty.department = g.department
            kind = subject.requirements_json.get("session_type", "LECTURE")
            if row.get("batch_number"):
                hours = 2  # each batch does the 2h practical once a week
            else:
                hours = subject.hours_per_week or 1
            # One row per (subject, group, batch, period) — the grid sometimes
            # carries the same subject twice (a LECTURE cell and a TUTORIAL cell
            # under the same code). Skip the duplicate rather than violate the
            # unique index.
            dedup_key = (subject.id, g.id,
                         row.get("batch_number"), row.get("period_id"))
            if dedup_key in seen_assignments:
                skipped += 1
                continue
            seen_assignments.add(dedup_key)
            db.add(SubjectAssignment(
                subject_id=subject.id, faculty_id=faculty.id, group_id=g.id,
                weekly_hours=hours, load_share=1.0,
                batch_number=row.get("batch_number"),
                period_number=row.get("period_id"),
            ))
            created += 1
        # The unique index (one row per subject/group/batch/period) means
        # auto-fill must not re-invent a row the grid already produced. Flush
        # the grid-derived assignments so the `has` check below sees them.
        db.flush()
        print(f"  assignments: {created} created, {skipped} skipped (unresolved)")

        # ── auto-fill: every subject in a class's profile must be taught ──
        # Some grids don't resolve to assignment rows (MBA name-codes, BE/FE
        # cells with unresolved faculty). For those, assign the class's first
        # department faculty deterministically so no subject silently vanishes;
        # the exact teacher is a college-data gap, this is the system's
        # suggestion. Labs get the standard 2-batch (SE+) / 3-batch (FE) split.
        auto = 0
        for name, g, dept_code in group_rows:
            dept_name = dept_by_code.get(dept_code, {}).get("name")
            # Branch-local pool ONLY — the shared "Faculty" bucket must never
            # serve a branch (that is what let one placeholder teacher burn his
            # weekly cap across five branches and starve the last one).
            dept_fac = sorted(
                (f for f in faculty_by_name.values() if f.department == dept_name),
                key=lambda f: f.id,
            )
            if not dept_fac:
                continue
            # Distribute subjects across the department's faculty (one subject
            # per slot of the pool) so no single teacher exceeds the weekly cap.
            subj_idx = 0
            for key, subject in subjects_by_key.items():
                if key[0] != dept_code or key[1] != g.semester:
                    continue
                has = db.scalar(select(func.count()).select_from(SubjectAssignment).where(
                    SubjectAssignment.subject_id == subject.id,
                    SubjectAssignment.group_id == g.id)) or 0
                if has:
                    continue
                is_lab = subject.requires_lab
                if is_lab:
                    batches = 3 if g.year == 1 else 2
                    for b in range(1, batches + 1):
                        db.add(SubjectAssignment(
                            subject_id=subject.id,
                            faculty_id=dept_fac[(g.id + subj_idx + b) % len(dept_fac)].id,
                            group_id=g.id, weekly_hours=subject.hours_per_week or 2,
                            load_share=1.0, batch_number=b, period_number=1,
                        ))
                        auto += 1
                else:
                    db.add(SubjectAssignment(
                        subject_id=subject.id,
                        faculty_id=dept_fac[(g.id + subj_idx) % len(dept_fac)].id,
                        group_id=g.id, weekly_hours=subject.hours_per_week or 1,
                        load_share=1.0,
                    ))
                    auto += 1
                subj_idx += 1
        print(f"  auto-fill assignments: {auto}")

        # Attach the group/subject/faculty/room resources to each profile.
        for name, g, dept_code in group_rows:
            prof = db.scalar(select(TimetableProfile).where(
                TimetableProfile.name == f"{dept_by_code[dept_code]['name']} — {name}"))
            if prof is None:
                continue
            _attach_profile_resources(
                db, prof, g, dept_code, rooms_by_code, rooms_by_dept,
                faculty_by_name, subjects_by_key,
                dept_by_code[dept_code]["name"])

        db.commit()
        counts = {
            "faculty": db.scalar(select(func.count()).select_from(Faculty)),
            "groups": db.scalar(select(func.count()).select_from(StudentGroup)),
            "rooms": db.scalar(select(func.count()).select_from(Room)),
            "subjects": db.scalar(select(func.count()).select_from(Subject)),
            "assignments": db.scalar(select(func.count()).select_from(SubjectAssignment)),
            "profiles": db.scalar(select(func.count()).select_from(TimetableProfile)),
        }
        print("import complete:")
        for k, v in counts.items():
            print(f"  {k:>12}: {v}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _make_profile(db, admin, name, sem, dept, rooms, faculty, groups,
                  grid, term_start, year, preferred_rooms=None,
                  break_slots=None, working_days=None, saturday_policy="NONE"):
    prof = TimetableProfile(name=name, scope_type=ScopeType.DIVISION,
                            academic_year="2026-27", semester=sem,
                            department=dept, created_by=admin.id)
    db.add(prof)
    db.flush()
    if grid:
        slots = grid.get("slots") or []
        if slots:
            db.add(ProfileParameter(profile_id=prof.id, param_key="slots_per_day",
                                    param_value=str(len(slots)), param_type=ParamType.INT))
            # Slot times are read verbatim from the published grid's rows (A2):
            # ``slot_times`` = [[start, end], ...] per teachable slot. The
            # synthetic day_start/slot_duration arithmetic is deleted for
            # imported grids — it drifted by an hour and a column.
            db.add(ProfileParameter(profile_id=prof.id, param_key="slot_times",
                                    param_value=json.dumps(
                                        [[s["start"], s["end"]] for s in slots]),
                                    param_type=ParamType.JSON))
        # The break is a numbered slot whose position varies per division; the
        # importer reads it from that division's BREAK cells (A2).
        if break_slots:
            db.add(ProfileParameter(profile_id=prof.id, param_key="break_slots",
                                    param_value=json.dumps(break_slots),
                                    param_type=ParamType.JSON))
    # Working days per division, derived from the days that actually carry
    # teaching cells in the published grid (not the grid header, which lists
    # Saturday even though COMP/IT/EXTC teach none).
    if working_days is not None:
        day_names = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        db.add(ProfileParameter(profile_id=prof.id, param_key="working_days",
                                param_value=json.dumps(
                                    [day_names[d] for d in working_days if 0 <= d <= 6]),
                                param_type=ParamType.JSON))
    else:
        days = (grid or {}).get("working_days") or [0, 1, 2, 3, 4]
        day_names = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        db.add(ProfileParameter(profile_id=prof.id, param_key="working_days",
                                param_value=json.dumps([day_names[d] for d in days]),
                                param_type=ParamType.JSON))
    db.add(ProfileParameter(profile_id=prof.id, param_key="saturday_policy",
                            param_value=saturday_policy, param_type=ParamType.STRING))
    db.add(ProfileParameter(profile_id=prof.id, param_key="term_start",
                            param_value=term_start, param_type=ParamType.STRING))
    if preferred_rooms:
        db.add(ProfileParameter(profile_id=prof.id, param_key="preferred_rooms",
                                param_value=json.dumps(preferred_rooms),
                                param_type=ParamType.JSON))
    # Labs are 2h blocks; at most one practical subject per day (real rules).
    db.add(HardConstraint(profile_id=prof.id, constraint_type="CONTIGUOUS_LAB_SLOTS",
                          config_json={"default_block_length": 2},
                          description="2h lab blocks (real TCET practicals)"))
    db.add(HardConstraint(profile_id=prof.id, constraint_type="MAX_ONE_LAB_PER_DAY",
                          config_json={}, description="max one practical subject per day"))
    # Soft scorer: how much of the division's load stays in its venue (A5).
    db.add(SoftConstraint(profile_id=prof.id, constraint_type="ROOM_STABILITY",
                          config_json={}, weight=1.0,
                          description="lectures stay in the division's home room(s)"))
    return prof


def _attach_profile_resources(db, prof, group, dept_code, rooms_by_code,
                              rooms_by_dept, faculty_by_name, subjects_by_key,
                              dept_name):
    # Branch-bound: a profile only sees its own branch's rooms and faculty, so a
    # teacher never appears teaching in two departments and the shared pool can
    # never starve the last branch.
    for r in rooms_by_dept.get(dept_code, []):
        db.add(ProfileResource(profile_id=prof.id, resource_type=ResourceType.ROOM,
                               resource_id=r.id))
    for f in faculty_by_name.values():
        if f.department == dept_name:
            db.add(ProfileResource(profile_id=prof.id, resource_type=ResourceType.FACULTY,
                                   resource_id=f.id))
    db.add(ProfileResource(profile_id=prof.id, resource_type=ResourceType.STUDENT_GROUP,
                           resource_id=group.id))
    sem = group.semester
    for key, s in subjects_by_key.items():
        if key[0] == dept_code and key[1] == sem:
            db.add(ProfileResource(profile_id=prof.id, resource_type=ResourceType.SUBJECT,
                                   resource_id=s.id))
    db.flush()


if __name__ == "__main__":
    sys.exit(main())
