"""Seed a realistic full-college dataset into Postgres for scale testing.

Mimics the TCET sample data (``sample/``): 12 departments, each with 4 years
(FE / SE / TE / BE) x 4 divisions (A-D) = 16 classes, one semester per year
(FE → Sem 1, SE → Sem 3, TE → Sem 5, BE → Sem 7), 6 subjects per year, one
subject-assignment per subject/division, and rooms/faculty scaled for 16
classes per department. Creates one DIVISION-scoped profile per (department,
year) — all four divisions scheduled together, the real college unit — plus
one DEPARTMENT-scoped profile per department, wired to the same solver
parameters the real TCET timetable uses (8 x 1h slots, 08:30 start, lunch
after slot 4, Mon-Sat, ``term_start`` anchored).

Usage:
    uv run python -m scripts.seed_demo [--wipe] [--or-tools-smoke]

``--wipe`` deletes all scheduling rows first (rooms/faculty/groups/subjects/
assignments/profiles/constraints/generations/history/audit) but keeps admins.
``--or-tools-smoke`` additionally prints the candidate-session count a couple
of representative profiles would feed OR-Tools (to sanity-check scale before a
real run).

This is a dev/testing tool, not part of the API surface.
"""
from __future__ import annotations

import argparse
import random
import sys

from sqlalchemy import text

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
from app.models import (
    TimetableGeneration, TimetableInstance, TimetableSlot,
    HardConstraint, SoftConstraint, TimetableHistory, TimetableResetLog,
    RoomBlackout, FacultyAvailability, AuditLog, ProfileCombination,
    ProfileCombinationMember,
)

# ── college shape (from the TCET sample) ────────────────────
DEPARTMENTS = [
    ("Computer Engineering", "COMP", 40),
    ("Information Technology", "IT", 35),
    ("Electronics & Telecommunication", "EXTC", 32),
    ("Electronics Engineering", "ELX", 28),
    ("Mechanical Engineering", "MECH", 34),
    ("Civil Engineering", "CIVIL", 28),
    ("Electrical Engineering", "ELEC", 26),
    ("Chemical Engineering", "CHEM", 24),
    ("Instrumentation Engineering", "INST", 22),
    ("Artificial Intelligence & Data Science", "AIDS", 26),
    ("Artificial Intelligence & ML", "AIML", 26),
    ("Computer Science & Business Systems", "CSBS", 24),
]

SEMESTERS = 8
DIVISIONS_PER_SEM = 2  # legacy: 2 divisions per semester (pre-rename)

# College class structure (the real TCET model): each year has FOUR divisions
# (A–D), and all divisions of a year are on the same semester. Years are named
# FE (first), SE (second), TE (third), BE (fourth). Semester mapping: FE → Sem 1,
# SE → Sem 3, TE → Sem 5, BE → Sem 7 (the odd semester of each academic year).
YEAR_LABELS = [(1, "FE"), (3, "SE"), (5, "TE"), (7, "BE")]
DIVISIONS = ["A", "B", "C", "D"]

ACADEMIC_YEAR = "2026-27"
# Real COMP-semester names/codes pulled from the syllabus PDFs where they
# exist; the same shape (2 labs + 4 theory) is applied to every department.
SEM_SUBJECTS = {
    1: [("Engineering Mathematics-I", "BSC-101", False),
        ("Engineering Physics", "BSC-102", False),
        ("Programming & Problem Solving (C)", "ESC-101", True),
        ("Basic Electrical & Electronics", "ESC-102", False),
        ("Communication Skills", "HSMC-101", False),
        ("Engineering Drawing", "ESC-103", True)],
    2: [("Engineering Mathematics-II", "BSC-201", False),
        ("Engineering Chemistry", "BSC-202", False),
        ("Data Structures & Algorithms", "PCC-201", True),
        ("Object Oriented Programming", "PCC-202", True),
        ("Basic Mechanical & Civil Engg", "ESC-201", False),
        ("Environmental Science", "MC-201", False)],
    3: [("Engineering Mathematics-III", "BSC-301", False),
        ("Digital Logic Design & Computer Arch", "ESC-301", False),
        ("Database Management System", "PCC-301", True),
        ("Discrete Structures", "PCC-302", False),
        ("Professional Skills-I", "MC-301", False),
        ("Universal Human Values-II", "HSMC-301", False)],
    4: [("Engineering Mathematics-IV", "BSC-401", False),
        ("Design & Analysis of Algorithms", "PCC-401", True),
        ("Operating System", "PCC-402", False),
        ("Computer Networks", "PCC-403", True),
        ("Software Engineering", "PCC-404", False),
        ("Environmental Studies", "MC-401", False)],
    5: [("Theory of Computation", "PCC-501", False),
        ("Intelligent Systems", "PCC-502", False),
        ("Microprocessors", "PCC-503", True),
        ("Computer Graphics", "PCC-504", True),
        ("Soft Skills & Interpersonal Comm.", "HSMC-501", False),
        ("Distributed Systems", "PEC-501", False)],
    6: [("System Programming & Compiler Const.", "PCC-601", False),
        ("Machine Learning", "PCC-602", True),
        ("Cloud Computing", "PEC-601", False),
        ("Mobile Computing", "PEC-602", False),
        ("Advanced Operating Systems", "PEC-603", False),
        ("Project Management", "HSMC-601", False)],
    7: [("Big Data Analytics", "PEC-701", True),
        ("Deep Learning", "PEC-702", True),
        ("Information Security", "PEC-703", False),
        ("Internet of Things", "PEC-704", False),
        ("Elective-I", "OEC-701", False),
        ("Internship & Seminar", "PROJ-701", False)],
    8: [("Major Project", "PROJ-801", True),
        ("Elective-II", "OEC-801", False),
        ("Elective-III", "OEC-802", False),
        ("Advanced Topics", "PEC-801", False),
        ("Entrepreneurship", "HSMC-801", False),
        ("Research Methodology", "MC-801", False)],
}

# Real COMP faculty from the TCET PDF, padded with generated names.
COMP_FACULTY = [
    "R.R. Sedamkar", "Sheetal Rathi", "Harshali P. Patil", "Megharani Patil",
    "Rekha Sharma", "Rashmi Thakur", "Vaishali Nirgude", "Shailesh Sangle",
    "Preksha Pareek", "Sudhir Mundhra", "Vikas Singh", "Lydia Suganya",
    "Veena Kulkarni", "Deepali Joshi", "Loukik Salvi", "Foram Shah",
    "Tanmayi Nagale", "Drashti Shrimal", "Siddhi Shekhar Ambre",
    "Swapnil Bhagat", "Sonali Chirag Gandhi", "Vinitta Sunish",
    "Ashish Kamlesh Dwivedi", "Hetal Rana", "Akshata Raut", "Mimansha Singh",
    "Soumyamol P.S", "Shushant Sawant", "Samir Sawant", "Roshani Sagar Baikar",
    "Neha Wankhede", "Rishab Dinesh Singh", "Vrunal Sandesh Gharat",
    "Shubham Parmekar", "Parth Mehta", "Pranisha Daishadhi", "Hema Rana",
    "Swati Swarnkar", "Namrata N", "Vishal Karle",
]

_FIRST = ["Aarav", "Priya", "Rohan", "Sneha", "Kiran", "Meera", "Aditya",
          "Ananya", "Vikram", "Kavita", "Nikhil", "Pooja", "Rahul", "Shreya",
          "Sandeep", "Neha", "Amit", "Ritu", "Gaurav", "Divya"]
_LAST = ["Patel", "Sharma", "Iyer", "Kulkarni", "Desai", "Joshi", "Rao",
         "Nair", "Gupta", "Mehta", "Singh", "Reddy", "Bhat", "Fernandes",
         "Chauhan", "Naik", "Pillai", "Hegde", "Thakur", "More"]


def _gen_faculty_names(count: int, rng: random.Random) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    while len(names) < count:
        n = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
        if n not in seen:
            seen.add(n)
            names.append(n)
    return names


def wipe_scheduling(db) -> None:
    """Delete every scheduling row (keeps admins and settings singleton)."""
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


def seed(db) -> dict:
    """Create the full college dataset. Returns a summary dict of counts."""
    counts: dict[str, int] = {k: 0 for k in (
        "departments", "subjects", "faculty", "groups", "rooms",
        "assignments", "profiles",
    )}

    # First admin row (the seeding admin is whoever was created first).
    from app.models.admin import Admin
    admin = db.query(Admin).first()
    if admin is None:
        from app.utils.auth import hash_password
        admin = Admin(email="seed@example.com", name="Seed Admin",
                      password=hash_password("seed123"))
        db.add(admin)
        db.flush()

    rng = random.Random(20260810)
    all_faculty: dict[str, list[Faculty]] = {}
    all_groups: dict[str, list[StudentGroup]] = {}
    all_rooms: dict[str, list[Room]] = {}
    all_subjects: dict[str, list[Subject]] = {}

    for dept_name, dept_code, fac_count in DEPARTMENTS:
        counts["departments"] += 1

        # ── rooms ─────────────────────────────────────────
        # Scaled for 4 divisions per year (16 classes per dept): more
        # classrooms and labs than the old 2-division seed needed, so a
        # whole-department run can fill a realistic week.
        rooms: list[Room] = []
        for c in range(1, 17):  # 16 classrooms
            rooms.append(Room(
                name=f"{dept_code}-CR{c}", room_code=f"{dept_code}-CR{c}",
                room_type=RoomType.CLASSROOM, capacity=80, building="Main",
                floor=((c - 1) % 4) + 1, has_projector=True, has_ac=(c % 2 == 0),
                equipment_json=["projector"] if c % 2 == 0 else [],
            ))
        for l in range(1, 11):  # 10 labs
            rooms.append(Room(
                name=f"{dept_code}-LAB{l}", room_code=f"{dept_code}-LAB{l}",
                room_type=RoomType.LAB, capacity=60, building="Main",
                floor=((l - 1) % 3) + 1, has_projector=False,
                equipment_json=["ac"],
            ))
        rooms.append(Room(
            name=f"{dept_code}-SEM", room_code=f"{dept_code}-SEM",
            room_type=RoomType.SEMINAR_HALL, capacity=60, building="Main",
            floor=3, has_projector=True, has_ac=True,
        ))
        db.add_all(rooms)
        db.flush()
        all_rooms[dept_code] = rooms
        counts["rooms"] += len(rooms)

        # ── faculty ────────────────────────────────────────
        names = list(COMP_FACULTY) if dept_code == "COMP" else _gen_faculty_names(fac_count, rng)
        faculty: list[Faculty] = []
        for i, name in enumerate(names):
            faculty.append(Faculty(
                name=name, email=f"{dept_code.lower()}.{i + 1}@tcet.edu.in",
                department=dept_name,
                max_hours_per_week=20, max_hours_per_day=6,
            ))
        db.add_all(faculty)
        db.flush()
        all_faculty[dept_code] = faculty
        counts["faculty"] += len(faculty)

        # ── groups: 4 divisions (A-D) per year, one semester per year ──
        # FE → Sem 1, SE → Sem 3, TE → Sem 5, BE → Sem 7. All four divisions of
        # a year share that semester (the real TCET class structure).
        groups: list[StudentGroup] = []
        for year, (sem, label) in enumerate(YEAR_LABELS, start=1):
            for div in DIVISIONS:
                groups.append(StudentGroup(
                    name=f"{dept_code}-{label}-{div}",
                    group_type=GroupType.DIVISION, department=dept_name,
                    year=year, semester=sem, strength=60,
                ))
        db.add_all(groups)
        db.flush()
        all_groups[dept_code] = groups
        counts["groups"] += len(groups)

        # ── subjects ──────────────────────────────────────
        # One subject set per year-semester (Sem 1/3/5/7), each with 6 subjects
        # (2 labs + 4 theory). Codes carry the year label so COMP-TE-3 reads as
        # "Computer Engineering, Third Year, subject 3".
        subjects: list[Subject] = []
        for sem, label in YEAR_LABELS:
            for j, (sname, code, is_lab) in enumerate(SEM_SUBJECTS[sem]):
                reqs = None
                if is_lab:
                    reqs = {"session_type": "LAB", "room_types": ["LAB"],
                            "min_capacity": 40}
                subjects.append(Subject(
                    name=f"{sname}", subject_code=f"{dept_code}-{label}-{j + 1}",
                    department=dept_name, semester=sem,
                    hours_per_week=3, requires_lab=is_lab,
                    requirements_json=reqs,
                ))
        db.add_all(subjects)
        db.flush()
        all_subjects[dept_code] = subjects
        counts["subjects"] += len(subjects)

        # ── assignments: each subject → one faculty per division ──
        assignments = 0
        faculty_rotor = 0
        for sem, label in YEAR_LABELS:
            sem_subjects = [s for s in subjects if s.semester == sem]
            sem_groups = [g for g in groups if g.semester == sem]
            for subj in sem_subjects:
                for grp in sem_groups:
                    fac = faculty[faculty_rotor % len(faculty)]
                    faculty_rotor += 1
                    db.add(SubjectAssignment(
                        subject_id=subj.id, faculty_id=fac.id, group_id=grp.id,
                        weekly_hours=subj.hours_per_week, load_share=1.0,
                    ))
                    assignments += 1
        counts["assignments"] += assignments

        # ── profiles ──────────────────────────────────────
        # (a) one DIVISION-scoped profile per CLASS — 16 per department
        # (4 years x 4 divisions). Each profile schedules exactly ONE division
        # (e.g. COMP-TE-B), so every class gets its own clean timetable with no
        # years merged.
        for sem, label in YEAR_LABELS:
            for div in DIVISIONS:
                group = next(g for g in groups
                             if g.semester == sem and g.name.endswith(f"-{div}"))
                prof = TimetableProfile(
                    name=f"{dept_name} — {label}-{div}",
                    scope_type=ScopeType.DIVISION,
                    academic_year=ACADEMIC_YEAR, semester=sem,
                    department=dept_name, created_by=admin.id,
                )
                db.add(prof)
                db.flush()
                _attach_resources(db, prof, rooms, faculty,
                                  [group],
                                  [s for s in subjects if s.semester == sem])
                _attach_params(db, prof)
                counts["profiles"] += 1

        # (b) one DEPARTMENT-scoped profile covering all four years
        prof = TimetableProfile(
            name=f"{dept_name} — All Sems", scope_type=ScopeType.DEPARTMENT,
            academic_year=ACADEMIC_YEAR, semester=None,
            department=dept_name, created_by=admin.id,
        )
        db.add(prof)
        db.flush()
        _attach_resources(db, prof, rooms, faculty, groups, subjects)
        _attach_params(db, prof)
        counts["profiles"] += 1

    db.commit()
    _provision_portal_accounts(db)
    db.commit()
    return counts


def _provision_portal_accounts(db) -> None:
    """Provision role-scoped logins so the teacher/student portals are
    demoable. The teacher logs in with a real Faculty row's email so /my
    resolves their schedule; the student's login email is set on a group's
    ``student_email`` so /my/timetable resolves their group; an HOD gets a
    standalone account.

    Credentials (all password ``teach123``):
      teacher:  <first faculty email>  (see the linked line printed at seed)
      student:  student1@tcet.edu.in  (linked to the first student group)
      hod:      hod@tcet.edu.in
    """
    from app.models.admin import Admin, AdminRole
    from app.utils.auth import hash_password
    from app.models.faculty import Faculty
    from app.models.groups import StudentGroup
    from sqlalchemy import select

    existing = {a.email: a for a in db.scalars(select(Admin)).all()}
    first_faculty = db.scalars(select(Faculty).order_by(Faculty.id)).first()
    first_group = db.scalars(select(StudentGroup).order_by(StudentGroup.id)).first()

    def ensure(email, name, role):
        # Always (re)set the portal password so the printed credential is
        # truthful even when the account pre-existed a re-seed.
        if email in existing:
            acc = existing[email]
            acc.password = hash_password("teach123")
            return
        db.add(Admin(email=email, name=name,
                     password=hash_password("teach123"),
                     role=role))

    ensure("student1@tcet.edu.in", "Student One", AdminRole.STUDENT)
    ensure("hod@tcet.edu.in", "HOD One", AdminRole.HOD)
    if first_faculty is not None:
        ensure(first_faculty.email, first_faculty.name, AdminRole.TEACHER)
        print(f"  teacher login: {first_faculty.email} / teach123 "
              f"({first_faculty.name})")
    if first_group is not None:
        first_group.student_email = "student1@tcet.edu.in"
        print(f"  student login: student1@tcet.edu.in / teach123 "
              f"(group {first_group.name})")
    db.flush()


def _attach_resources(db, prof, rooms, faculty, groups, subjects) -> None:
    for r in rooms:
        db.add(ProfileResource(profile_id=prof.id,
                               resource_type=ResourceType.ROOM, resource_id=r.id))
    for f in faculty:
        db.add(ProfileResource(profile_id=prof.id,
                               resource_type=ResourceType.FACULTY, resource_id=f.id))
    for g in groups:
        db.add(ProfileResource(profile_id=prof.id,
                               resource_type=ResourceType.STUDENT_GROUP,
                               resource_id=g.id))
    for s in subjects:
        db.add(ProfileResource(profile_id=prof.id,
                               resource_type=ResourceType.SUBJECT, resource_id=s.id))


def _attach_params(db, prof) -> None:
    """The TCET grid: 8 x 1h slots, 08:30 start, lunch after slot 4, Mon-Sat."""
    params = {
        "slots_per_day": ("8", ParamType.INT),
        "day_start_time": ("08:30", ParamType.STRING),
        "slot_duration_minutes": ("60", ParamType.INT),
        "lunch_break_after_slot": ("4", ParamType.INT),
        "lunch_break_duration_minutes": ("60", ParamType.INT),
        "working_days": ('["MON","TUE","WED","THU","FRI","SAT"]', ParamType.JSON),
        "term_start": ("2026-07-06", ParamType.STRING),
    }
    for key, (value, ptype) in params.items():
        db.add(ProfileParameter(profile_id=prof.id, param_key=key,
                                param_value=value, param_type=ptype))


def _or_tools_smoke(db) -> None:
    """Print candidate-session scale for OR-Tools on two representative profiles."""
    from sqlalchemy import select
    from app.engine.profile_resolver import ProfileResolver
    from app.engine.resource_requirements import effective_requirements, subject_session_type
    from app.models.generation import SessionType

    profiles = db.scalars(select(TimetableProfile).where(
        TimetableProfile.name.like("%— TE-A%"))).all()
    for prof in profiles[:2]:
        resolved = ProfileResolver(db).resolve(prof.id)
        subj_ids = resolved.resource_ids(ResourceType.SUBJECT)
        sessions = 0
        for a in db.scalars(select(SubjectAssignment).where(
                SubjectAssignment.subject_id.in_(subj_ids))).all():
            sessions += a.weekly_hours or 0
        print(f"  OR-Tools candidate sessions for '{prof.name}': ~{sessions} "
              f"({len(subj_ids)} subjects)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wipe", action="store_true",
                        help="truncate all scheduling tables before seeding")
    parser.add_argument("--or-tools-smoke", action="store_true",
                        help="print OR-Tools session counts for a couple profiles")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.wipe:
            print("wiping scheduling tables…")
            wipe_scheduling(db)
        counts = seed(db)
        print("seed complete:")
        for k, v in counts.items():
            print(f"  {k:>12}: {v}")
        if args.or_tools_smoke:
            _or_tools_smoke(db)
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
