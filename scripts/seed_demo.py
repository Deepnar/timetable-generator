"""Seed a realistic full-college dataset into Postgres for scale testing.

Mimics the TCET sample data (``sample/``): 12 departments, each with 4 years
(FE / SE / TE / BE) x 4 divisions (A-D) = 16 classes, one semester per year
(FE → Sem 1, SE → Sem 3, TE → Sem 5, BE → Sem 7), 7 subjects per year (split
into lecture/tutorial/lab streams per the REAL TCET scheme), one
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
    # (name, code, faculty count). Scaled for 16 classes x 6 subjects = 96
    # assignments per department at ~28h/class (448h/wk of teaching): with
    # max_hours_per_week=20 the pool needs ~30+ faculty so the assignment rotor
    # never overloads one teacher, which starved later classes of unreserved
    # faculty slots (cross-timetable) and made OR-Tools drop sessions.
    ("Computer Engineering", "COMP", 64),
    ("Information Technology", "IT", 56),
    ("Electronics & Telecommunication", "EXTC", 52),
    ("Electronics Engineering", "ELX", 48),
    ("Mechanical Engineering", "MECH", 54),
    ("Civil Engineering", "CIVIL", 48),
    ("Electrical Engineering", "ELEC", 46),
    ("Chemical Engineering", "CHEM", 44),
    ("Instrumentation Engineering", "INST", 42),
    ("Artificial Intelligence & Data Science", "AIDS", 46),
    ("Artificial Intelligence & ML", "AIML", 46),
    ("Computer Science & Business Systems", "CSBS", 44),
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
# Real COMP scheme extracted from the sample PDFs (TCET CBCGS-HME 2023).
# Each subject is modeled as its LECTURE / TUTORIAL / LAB streams, matching the
# actual class timetable: theory = 3 x 1h lectures, tutorial = 1h, practical =
# a 2h lab block. ~7 subjects per semester -> ~29 contact hours/week per class
# (the TE-D timetable: 16 theory + 1 tutorial + 12 practical hours).
# Stream tuples: (name, code, session_kind, hours_per_week)
#   session_kind: "L" lecture, "T" tutorial, "P" practical (2h lab block)
REAL_SCHEME = {
    1: [
        ("Engineering Mathematics-I", "BSC-101", "L", 3),
        ("Engineering Mathematics-I", "BSC-101", "T", 1),
        ("Engineering Physics", "BSC-102", "L", 3),
        ("Engineering Physics Lab", "BSC-102", "P", 2),
        ("Programming & Problem Solving (C)", "PPS", "L", 3),
        ("Programming & Problem Solving Lab", "PPS", "P", 2),
        ("Basic Electrical & Electronics", "BEE", "L", 3),
        ("Basic Electrical & Electronics Lab", "BEE", "P", 2),
        ("Communication Skills", "HSMC-101", "L", 3),
        ("Engineering Drawing", "ESC-103", "P", 2),
    ],
    3: [
        ("Universal Human Values-II", "HSMC-301", "L", 2),
        ("Engineering Mathematics-III", "BSC-301", "L", 3),
        ("Engineering Mathematics-III", "BSC-301", "T", 1),
        ("Digital Logic Design & Computer Architecture", "DLD", "L", 3),
        ("Digital Logic Design Lab", "DLD", "P", 2),
        ("Database Management System", "DBMS", "L", 3),
        ("Database Management System Lab", "DBMS", "P", 2),
        ("Data Structure using Java", "DS", "L", 3),
        ("Data Structure using Java Tut", "DS", "T", 1),
        ("Data Structure using Java Lab", "DS", "P", 2),
        ("Professional Skills-I", "PS-301", "P", 2),
    ],
    4: [
        ("Engineering Mathematics-IV", "BSC-401", "L", 3),
        ("Engineering Mathematics-IV", "BSC-401", "T", 1),
        ("Design & Analysis of Algorithm using Python", "DAA", "L", 3),
        ("DAA Lab", "DAA", "P", 2),
        ("Operating System", "OS", "L", 3),
        ("Operating System Lab", "OS", "P", 2),
        ("Computer Networks", "CN", "L", 3),
        ("Computer Networks Lab", "CN", "P", 2),
        ("Professional Skills-II", "PS-401", "P", 2),
        ("Environmental Studies", "MC-401", "L", 1),
    ],
    5: [
        ("Soft Skill & Interpersonal Communication", "SSIC", "L", 3),
        ("Computer Graphics", "CG", "L", 3),
        ("Computer Graphics Lab", "CG", "P", 2),
        ("Theory of Computation", "TOC", "L", 3),
        ("Theory of Computation Tut", "TOC", "T", 1),
        ("Introduction to Intelligent Systems", "IIS", "L", 3),
        ("Intelligent Systems Lab", "IIS", "P", 2),
        ("Microprocessor", "MP", "L", 3),
        ("Microprocessor Lab", "MP", "P", 2),
        ("Professional Skills-IV", "PS-501", "P", 2),
        ("Indian Constitution", "MC-501", "L", 1),
    ],
    6: [
        ("Work Place Mental Health", "HSMC-601", "L", 2),
        ("System Programming & Compiler Construction", "SPCC", "L", 3),
        ("SPCC Lab", "SPCC", "P", 2),
        ("Software Engineering", "SE", "L", 3),
        ("Software Engineering Lab", "SE", "P", 2),
        ("Professional Elective-I", "PEC-601", "L", 3),
        ("Open Elective-I", "OEC-601", "L", 3),
        ("Research Based Learning", "RBL-601", "P", 2),
        ("Professional Skills-V", "PS-601", "P", 2),
    ],
    7: [
        ("Data Warehousing and Mining", "DWM", "L", 3),
        ("DWM Lab", "DWM", "P", 2),
        ("Cryptography and System Security", "CSS", "L", 3),
        ("Cryptography Lab", "CSS", "P", 2),
        ("Professional Elective-II", "PEC-701", "L", 3),
        ("Professional Elective-II Lab", "PEC-701", "P", 2),
        ("Professional Elective-III", "PEC-702", "L", 3),
        ("Open Elective-II", "OEC-701", "L", 3),
        ("Project-I", "PROJ-701", "P", 4),
    ],
    8: [
        ("Distributed Computing", "PCC-801", "L", 3),
        ("Software Architecture", "PCC-802", "L", 3),
        ("Professional Elective-IV", "PEC-801", "L", 3),
        ("Professional Elective-IV Lab", "PEC-801", "P", 2),
        ("Open Elective-III", "OEC-801", "L", 3),
        ("Project-II", "PROJ-801", "P", 12),
    ],
}

# Map session kind -> (session_type, hours, requirements)
def _stream_spec(kind: str):
    if kind == "P":
        return {"session_type": "LAB", "room_types": ["LAB"], "min_capacity": 40}
    if kind == "T":
        return {"session_type": "TUTORIAL", "room_types": ["CLASSROOM"]}
    return {"session_type": "LECTURE", "room_types": ["CLASSROOM"]}

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
        # Subjects mirror the REAL TCET scheme (see REAL_SCHEME): each subject
        # is split into its lecture / tutorial / lab streams so a class's week
        # matches the reference timetable — 3 x 1h lectures, 1h tutorial, 2h
        # lab blocks, ~29 contact hours/week (16 theory + 1 tutorial + 12 lab).
        subjects: list[Subject] = []
        for sem, label in YEAR_LABELS:
            for (sname, code, kind, hours) in REAL_SCHEME.get(sem, []):
                reqs = _stream_spec(kind)
                subjects.append(Subject(
                    name=f"{sname}",
                    subject_code=f"{dept_code}-{label}-{code}-{kind}",
                    department=dept_name, semester=sem,
                    hours_per_week=hours,
                    requires_lab=(kind == "P"),
                    requirements_json=reqs,
                ))
        db.add_all(subjects)
        db.flush()
        all_subjects[dept_code] = subjects
        counts["subjects"] += len(subjects)

        # ── assignments: each class gets a DEDICATED faculty team ──
        # The cleanest way to get every class a full, unbroken morning is to
        # give each class its own teachers: 16 classes per department each take
        # a distinct slice of the faculty pool (~4 teachers cover the 6
        # subjects). No teacher crosses classes, so publishing one class never
        # reserves teachers that block another class's morning slots — the
        # cross-timetable contention that scattered sessions disappears.
        assignments = 0
        class_names = [
            f"{label}-{div}" for label in (l for _s, l in YEAR_LABELS)
            for div in DIVISIONS
        ]
        per_class = max(3, len(faculty) // len(class_names))
        for ci, cls_name in enumerate(class_names):
            label = cls_name.split("-")[0]
            sem = next(s for s, l in YEAR_LABELS if l == label)
            div = cls_name.split("-")[1]
            grp = next(g for g in groups if g.semester == sem and g.name.endswith(f"-{div}"))
            team_start = (ci * per_class) % len(faculty)
            team = [faculty[(team_start + i) % len(faculty)]
                    for i in range(per_class)]
            sem_subjects = [s for s in subjects if s.semester == sem]
            for j, subj in enumerate(sem_subjects):
                fac = team[j % len(team)]
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
    """The TCET grid: 8 x 1h slots, 08:30 start, lunch after slot 4, Mon-Sat.

    Also attaches the CONTIGUOUS_LAB_SLOTS hard rule with default_block_length=2
    so every practical subject's weekly hours are scheduled as 2h lab blocks —
    matching the reference timetable's "Lab X D1 D2" 2-period sessions.
    """
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
    # Labs are 2h blocks.
    db.add(HardConstraint(
        profile_id=prof.id,
        constraint_type="CONTIGUOUS_LAB_SLOTS",
        config_json={"default_block_length": 2},
        description="Seed: 2h lab blocks (real TCET practicals)",
    ))


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
