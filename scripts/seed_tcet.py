"""Seed the database with the REAL TCET college structure (from ``info/``).

Replaces the fabricated demo seed (``scripts/seed_demo.py`` — invented
departments ELX/ELEC/CHEM/INST/CSBS, uniform FE-under-every-department, 176
faculty/dept, strength 60, made-up FE scheme) with the actual college as
scraped from tcetmumbai.in (see ``info/`` and ``sample/esah_fe_department_info.md``).

What is real and where it came from:
- 13 departments (12 UG engineering branches + ES&H) — ``info/02-departments/``.
- FE is owned by the **Engineering Sciences & Humanities (ES&H)** department;
  FE divisions are per-intake (COMP has 4 this year). FE splits into two
  streams: Group I (COMP, CSE-CS, CIVIL, CSE-IoT, AI&DS) starts on the Physics
  stream, Group 2 (IT, MECH, EXTC, E&CS, MME, AI&ML) on the Chemistry stream.
- Real FE Sem I/II, SE Sem III, TE Sem V, BE Sem VII subject lists — from the
  result registers and the real division timetables (``info/05-courses-and-results.md``,
  ``info/03-timetables/class/UG/``).
- Real faculty names — ``info/04-faculty-directory.md`` + per-dept rosters.
- Real numbered rooms from the timetable venues.
- Grids: SE/TE = 9 x 1h from 08:30 with a break after slot 4, Saturday = IP;
  BE = no Saturday; FE = 08:00 start.

Division counts for non-COMP branches, exact strengths, and room capacities are
NOT published (honest gap) — the seed uses documented defaults an admin edits.

Usage:
    uv run python -m scripts.seed_tcet [--wipe]
"""
from __future__ import annotations

import argparse
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
    HardConstraint, SoftConstraint, ProfileCombination, ProfileCombinationMember,
)


# ── real departments (info/02-departments) ───────────────────
# name, code, FE group (I = Physics stream first, II = Chemistry stream first),
# FE division count this year, SE/TE/BE division counts (SE, TE, BE)
DEPARTMENTS = [
    # (name, code, fe_group, fe_divs, se_divs, te_divs, be_divs, fe_strength)
    ("Computer Engineering",            "COMP",  "I",  4, 4, 4, 3, 63),
    ("Information Technology",          "IT",    "II", 2, 4, 3, 3, 60),
    ("Electronics & Telecommunication", "EXTC",  "II", 2, 2, 2, 2, 60),
    ("Electronics & Computer Science",  "E&CS",  "II", 2, 1, 1, 1, 60),
    ("Mechanical Engineering",          "MECH",  "II", 2, 1, 1, 1, 60),
    ("Civil Engineering",               "CIVIL", "I",  2, 1, 1, 1, 60),
    ("Computer Science & Engineering (Cyber Security)", "CS&E", "I", 2, 1, 1, 1, 60),
    ("Mechanical & Mechatronics Engineering", "MME", "II", 2, 1, 1, 1, 60),
    ("Artificial Intelligence & Machine Learning", "AI&ML", "II", 2, 3, 1, 1, 60),
    ("Artificial Intelligence & Data Science", "AI&DS", "I", 2, 1, 1, 1, 60),
    ("Internet of Things",              "IoT",   "II", 2, 1, 1, 1, 60),
    ("Computer Science & Engineering (IoT)", "CSE-IoT", "I", 2, 1, 1, 1, 60),
    # ES&H owns all FE; the division rows are created below per intake.
    ("Engineering Sciences & Humanities", "ES&H", "I", 0, 0, 0, 0, 0),
]

# FE streams — Group I starts on Physics (odd), Group 2 on Chemistry.
# Each stream: (name, code, kind, hours) kind L/T/P. Fillers are (kind "F").
FE_PHYSICS_STREAM = [  # odd sem for Group I
    ("Engineering Mathematics-I", "BSC1102", "L", 3),
    ("Engineering Mathematics-I", "BSC1102", "T", 1),
    ("Engineering Physics", "BSC1101", "L", 3),
    ("Engineering Physics", "BSC1101", "P", 2),
    ("Basic Electrical Engineering", "ESC1101", "L", 3),
    ("Basic Electrical Engineering", "ESC1101", "P", 2),
    ("Engineering Graphics & Design", "ESC1102", "P", 2),
    ("English for General & Professional Communication", "HSMC1101", "L", 2),
    ("Attitude & Aptitude Development-I", "MC1101", "F", 1),
    ("Workshop & Manufacturing Practices-I", "ESC1103", "F", 2),
]
FE_CHEMISTRY_STREAM = [  # odd sem for Group II
    ("Engineering Mathematics-II", "BSC2101", "L", 3),
    ("Engineering Mathematics-II", "BSC2101", "T", 1),
    ("Engineering Chemistry", "BSC1201", "L", 3),
    ("Engineering Chemistry", "BSC1201", "P", 2),
    ("Programming for Problem Solving", "ESC1201", "L", 3),
    ("Programming for Problem Solving", "ESC1201", "P", 2),
    ("Engineering Mechanics", "BSC2102", "L", 3),
    ("Engineering Mechanics", "BSC2102", "P", 2),
    ("Introduction to Indian Knowledge System", "HSMC2101", "F", 2),
    ("Professional Skills-I", "HME-PS2101", "F", 2),
    ("Attitude & Aptitude Development-II", "MC2101", "F", 1),
]

# SE / TE / BE subject schemes per branch. Streams are (name, code, kind, hours).
# COMP is fully ground-truthed; the other branches use the real SE III / BE VII
# subject names from the exam registers, with a sensible T/L/P split.
BRANCH_SCHEMES = {
    "COMP": {
        3: [  # SE Sem III (real)
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
            ("Professional Skills-II", "PS-301", "F", 2),
        ],
        5: [  # TE Sem V (real)
            ("Soft Skill & Interpersonal Communication", "SSIC", "L", 3),
            ("Computer Graphics", "CG", "L", 3),
            ("Computer Graphics Lab", "CG", "P", 2),
            ("Theory of Computer Science", "TOC", "L", 3),
            ("Theory of Computer Science Tut", "TOC", "T", 1),
            ("Introduction to Intelligent System", "IIS", "L", 3),
            ("Intelligent System Lab", "IIS", "P", 2),
            ("Microprocessor", "MP", "L", 3),
            ("Microprocessor Lab", "MP", "P", 2),
            ("Indian Constitution", "MC-501", "F", 1),
            ("Professional Skills-IV", "PS-501", "F", 2),
        ],
        7: [  # BE Sem VII (real)
            ("Data Warehousing and Mining", "DWM", "L", 3),
            ("Data Warehousing and Mining Lab", "DWM", "P", 2),
            ("Cryptography and System Security", "CSS", "L", 3),
            ("Cryptography Lab", "CSS", "P", 2),
            ("Professional Elective-II", "PEC-701", "L", 3),
            ("Professional Elective-II Lab", "PEC-701", "P", 2),
            ("Professional Elective-III", "PEC-702", "L", 3),
            ("Open Elective-II", "OEC-701", "L", 3),
            ("Project-I", "PROJ-701", "P", 4),
        ],
    },
    "IT": {
        3: [
            ("Universal Human Values-II", "UHV-301", "L", 2),
            ("Engineering Mathematics-III", "BSC-301", "L", 3),
            ("Digital Circuit Design", "DCD", "L", 3),
            ("Database Management Systems", "DBMS", "L", 3),
            ("Database Management Systems Lab", "DBMS", "P", 2),
            ("Automata Theory", "AT", "L", 3),
            ("Cryptography and Network Security", "CNS", "L", 3),
            ("Soft Skill & Interpersonal Communication", "SSIC", "L", 2),
            ("Professional Skills-II", "PS-301", "F", 2),
        ],
        7: [
            ("Distributed Computing", "DC", "L", 3),
            ("Software Architecture", "SA", "L", 3),
            ("Professional Elective-II", "PEC-701", "L", 3),
            ("Open Elective-II", "OEC-701", "L", 3),
            ("Project-I", "PROJ-701", "P", 4),
        ],
    },
    "EXTC": {
        3: [
            ("Universal Human Values-II", "UHV-301", "L", 2),
            ("Networks & Control Engineering", "NCE", "L", 3),
            ("Digital Logic Design", "DLD", "L", 3),
            ("Discrete Time Signal Processing", "DTSP", "L", 3),
            ("Professional Skills-II", "PS-301", "F", 2),
        ],
        7: [
            ("Mobile Communication Systems", "MCS", "L", 3),
            ("Professional Elective-II", "PEC-701", "L", 3),
            ("Open Elective-II", "OEC-701", "L", 3),
            ("Project-I", "PROJ-701", "P", 4),
        ],
    },
    "E&CS": {
        3: [
            ("Universal Human Values-II", "UHV-301", "L", 2),
            ("Digital Circuits Design", "DCD", "L", 3),
            ("Database Management Systems", "DBMS", "L", 3),
            ("Signals and Systems", "SS", "L", 3),
            ("Operating Systems", "OS", "L", 3),
        ],
        7: [
            ("Robotics and Computer Vision", "RCV", "L", 3),
            ("Professional Elective-II", "PEC-701", "L", 3),
            ("Open Elective-II", "OEC-701", "L", 3),
            ("Project-I", "PROJ-701", "P", 4),
        ],
    },
    "MECH": {
        3: [
            ("Universal Human Values-II", "UHV-301", "L", 2),
            ("Mechanics of Materials", "MoM", "L", 3),
            ("Manufacturing Process", "MP", "L", 3),
            ("Mechanical Measurements and Metrology", "MMM", "L", 3),
            ("Soft Skill & Interpersonal Communication", "SSIC", "L", 2),
        ],
        7: [
            ("Design of Power Transmission Devices", "DPTD", "L", 3),
            ("Professional Elective-II", "PEC-701", "L", 3),
            ("Open Elective-II", "OEC-701", "L", 3),
            ("Project-I", "PROJ-701", "P", 4),
        ],
    },
    "CIVIL": {
        3: [
            ("Universal Human Values-II", "UHV-301", "L", 2),
            ("Civil Engineering Drawings", "CED", "P", 2),
            ("Reinforced Concrete Structure", "RCS", "L", 3),
            ("Applied Hydraulics", "AH", "L", 3),
            ("Soft Skill & Interpersonal Communication", "SSIC", "L", 2),
        ],
        7: [
            ("Professional Elective-II", "PEC-701", "L", 3),
            ("Open Elective-II", "OEC-701", "L", 3),
            ("Project-I", "PROJ-701", "P", 4),
        ],
    },
}

# Real faculty rosters (info/04-faculty-directory.md). Truncated to the published
# names; more can be added by an admin.
FACULTY = {
    "COMP": [
        "Dr. R. R. Sedamkar", "Dr. Sheetal Rathi", "Dr. Rashmi Thakur",
        "Dr. Vaishali Kaiche", "Dr. Shailesh Sangle", "Dr. Harshali P. Patil",
        "Dr. Megharani Patil", "Dr. Rekha Sharma", "Mr. Vikas Singh",
        "Mrs. Lydia Suganya", "Mrs. Veena Kulkarni", "Mrs. Deepali Joshi",
        "Dr. Loukik Salvi", "Ms. Foram Shah", "Ms. Siddhi Ambre",
        "Ms. Tanmayi Nagale", "Ms. Drashti Shrimal", "Ms. Pratiksha Deshmukh",
        "Mr. Swapnil Bhagat", "Mr. Ashish Dwivedi", "Ms. Abhilasha Patil",
        "Mrs. Sonali Chirag Gandhi", "Mrs. Vinitta Sunish", "Ms. Akshata Raut",
        "Ms. Mimansha Singh", "Mr. Sudhir Mundhra", "Mr. Shubham Parnekar",
        "Mr. Parth Mehta", "Mr. Samir Sawant", "Mr. Shushant Sawant",
        "Ms. Roshani Baikar", "Mr. Venkatesh Jamardarkhana", "Ms. Neha Wankhede",
        "Dr. Garima Joshi", "Mr. Rishab Singh", "Ms. Vrunal Gharat",
    ],
    "ES&H": [
        "Dr. Rohit Kumar Singh", "Dr. Sunita Pachori", "Dr. Ashwin Pathak",
        "Dr. Vinita Agarwal", "Mr. Yogesh Ganpat Bhalekar", "Dr. Rajni Bahuguna",
        "Dr. Krishnakant Mishra", "Dr. Sajjan Kumar Lal", "Dr. Satish Kumar Singh",
        "Dr. Ela Agarkar", "Ms. Sonali Singh", "Lt Dr. Nivant Kambale",
        "Mr. Vinod Salunkhe", "Ms. Priyanka Deshmukh", "Ms. Jyoti Vanawe",
        "Mr. Vikas Nagve", "Mr. Sohail Khadpolkar", "Mr. Shivram Poojari",
        "Dr. Karuna Nikum", "Dr. Achala Khandelwal", "Mr. Mahesh Biradar",
        "Dr. Savita Chandel", "Dr. Sheenu Gupta", "Dr. Asha Bhave",
        "Mr. Tulshiram Kudale", "Mr. Bhaskar Hambarde", "Mr. Brijesh Gupta",
        "Dr. Sainath Bhavsar", "Dr. Nidhi Tiwari", "Dr. Sneha Khandait",
        "Mr. Shrikrishna Sonawane", "Mr. Vijay Laxman Kale", "Dr. Pooja Singh",
        "Ms. Tanvi Shah", "Dr. Jitendra Patil", "Mr. Ansari Shakeel",
        "Dr. Tamanna Upadhyay", "Mrs. Mariyam Khan", "Dr. Suchitra Nirudas Sapakal",
        "Mr. Swapnil Alhat", "Dr. Balaji Shinde", "Dr. Sultana Begam",
        "Mr. Karthik Sankararaman", "Mr. Suraj Singh", "Ms. Soma Karmokar",
        "Ms. Sonal Gaikwad", "Ms. Bhumika Malhotra", "Ms. Prajakta Kamble",
        "Ms. Yogita Sagare Honrao", "Ms. Aafiya Siddiqui", "Mrs. Kinjal Dave",
        "Ms. Kavita Mhaskar", "Mrs. Chitralekha Vangale", "Ms. Amruta Malali",
        "Ms. Sakshi Pandey", "Ms. Dimple Bachelal Yadav", "Dr. Sharanu",
        "Mr. Prajual Kotian", "Dr. Kavita Bani", "Mr. Ninad Mahadeshwar",
    ],
    "IT": [
        "Dr. Rajesh Bansode", "Dr. Neeta P. Patil", "Dr. Sangeeta Vhatkar",
        "Dr. Anil K. Vasoya", "Dr. Aruna Pavate", "Dr. Namdeo Badhe",
        "Dr. Rahul Neve", "Mr. Santanu Das", "Ms. Pranjali Kasture",
        "Mr. Vijaykumar Yele", "Dr. Purvi Sankhe", "Mrs. Mary Margarat V",
        "Dr. Neha Patwari", "Mrs. Swati Chiplunkar", "Mrs. Apeksha Waghmare",
        "Mrs. Minakshi Ghorpade", "Mrs. Monisha Linkesh", "Mrs. Pratibha Prasad",
        "Mrs. Trupti Shah", "Ms. Komal Dhule", "Ms. Kriti Das",
        "Ms. Nidhi Bhavsar", "Ms. Anamika Singh", "Ms. Jisha Tinsu",
        "Mr. Manivannan Panchanatham", "Ms. Kajal Patel", "Mrs. Archita Agar",
        "Dr. Ranjita Asati", "Ms. Shradha Birje", "Ms. Siddeshwari Patil",
    ],
    "EXTC": [
        "Dr. Lochan Jolly", "Dr. Payel Saha", "Dr. Sangeeta Mishra",
        "Cdr. Vijay Pratap Singh", "Dr. Shailendra Shastri", "Dr. Manoj Chavan",
        "Ms. Sonia Behra", "Ms. Archana Deshpande", "Dr. Sukruti Kaulgud",
        "Mr. Deepak Shete", "Ms. Anvita Birje", "Ms. Megha Gupta",
        "Ms. Rupali Mane", "Ms. Rashmita K Mohapatra", "Mr. Nikhil Tiwari",
        "Mr. Niket Amoda", "Ms. Purnima Chandrasekar", "Dr. Vinitkumar Dongre",
    ],
    "MECH": [
        "Dr. Uddhav Nimbalkar", "Dr. Siddesh Doddametikurke", "Dr. Ankush Biradar",
        "Dr. Mahendra Shelar", "Mr. Vaibhav Madane", "Mr. Pawan Kumar Tiwari",
        "Mr. Pankaj Rawool",
    ],
    "CIVIL": [
        "Dr. Seema Jagtap", "Dr. Sanjeev Chaudhari", "Dr. Mehboobsab Nadaf",
        "Mrs. Rutuja Shinde",
    ],
}

# Real numbered venues from the division timetables (classrooms + labs). Extra
# rooms are synthesized where the site only names a few.
def _rooms_for(dept_code: str) -> list[tuple[str, str, int]]:
    """(name, room_type, capacity) for a branch; capacities are estimates."""
    classroom, lab, cap = f"{dept_code}-CR", f"{dept_code}-LAB", 60
    rooms = [
        (f"{dept_code}-CR1", "CLASSROOM", 60),
        (f"{dept_code}-CR2", "CLASSROOM", 60),
        (f"{dept_code}-LAB1", "LAB", 40),
        (f"{dept_code}-LAB2", "LAB", 40),
    ]
    return rooms


_FIRST = ["Aarav", "Priya", "Rohan", "Sneha", "Kiran", "Meera", "Aditya",
          "Ananya", "Vikram", "Kavita", "Nikhil", "Pooja", "Rahul", "Shreya",
          "Sandeep", "Neha", "Amit", "Ritu", "Gaurav", "Divya"]
_LAST = ["Patel", "Sharma", "Iyer", "Kulkarni", "Desai", "Joshi", "Rao",
         "Nair", "Gupta", "Mehta", "Singh", "Reddy", "Bhat", "Fernandes",
         "Chauhan", "Naik", "Pillai", "Hegde", "Thakur", "More"]


def _synthetic_names(code: str, count: int) -> list[str]:
    """Names for branches that publish no roster (AI&DS, IoT, CSE-IoT, CS&E, MME).

    Placeholders an admin replaces with the real roster. Deterministic per code.
    """
    rng = __import__("random").Random(hash(code) & 0xFFFF)
    out, seen = [], set()
    while len(out) < count:
        n = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


YEAR_SEMS = {1: 1, 2: 3, 3: 5, 4: 7}


def _stream_spec(kind: str) -> dict:
    if kind == "P":
        return {"session_type": "LAB", "room_types": ["LAB"], "min_capacity": 40}
    if kind == "T":
        return {"session_type": "TUTORIAL", "room_types": ["CLASSROOM"]}
    if kind == "F":
        return {"session_type": "ACTIVITY", "room_types": ["CLASSROOM"]}
    return {"session_type": "LECTURE", "room_types": ["CLASSROOM"]}


def wipe(db) -> None:
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
    from app.models.admin import Admin
    admin = db.query(Admin).first()
    if admin is None:
        from app.utils.auth import hash_password
        admin = Admin(email="seed@example.com", name="Seed Admin",
                      password=hash_password("seed123"))
        db.add(admin)
        db.flush()

    counts = {k: 0 for k in ("faculty", "groups", "rooms", "subjects",
                             "assignments", "profiles")}

    # ── ES&H owns FE. Create the FE subjects once, then every FE division's
    # profile attaches the stream its intake group starts on.
    esh_faculty = _make_faculty(db, "Engineering Sciences & Humanities", "ES&H",
                                FACULTY["ES&H"])
    counts["faculty"] += len(esh_faculty)
    esh_rooms = _make_rooms(db, "ES&H", _rooms_for("ES&H"))
    counts["rooms"] += len(esh_rooms)
    fe_subjects = _make_subjects(db, "Engineering Sciences & Humanities",
                                 [(1, FE_PHYSICS_STREAM), (2, FE_CHEMISTRY_STREAM)],
                                 prefix="FE")
    counts["subjects"] += len(fe_subjects)

    fe_groups: dict[str, list[StudentGroup]] = {}
    for name, code, fe_group, fe_divs, *_ in DEPARTMENTS:
        if code == "ES&H":
            continue
        # FE divisions live under ES&H, named by intake (COMP-A, COMP-B, ...).
        divs = []
        for div in "ABCD"[:fe_divs]:
            g = StudentGroup(
                name=f"{code}-FE-{div}", group_type=GroupType.DIVISION,
                department="Engineering Sciences & Humanities",
                # Group I starts on the Physics stream (odd sem); Group 2 on
                # the Chemistry stream. The stored stream semester tags which.
                year=1, semester=(1 if fe_group == "I" else 2),
                strength=63 if code == "COMP" else 60,
            )
            db.add(g)
            divs.append(g)
        db.flush()
        fe_groups[code] = divs
        counts["groups"] += len(divs)

    # FE assignments: each FE division's lab practicals get one faculty per batch
    # (3 batches). The Physics stream labs run on odd sem (Group I), Chemistry
    # stream on even — each division schedules the stream its group started on.
    for code, divs in fe_groups.items():
        stream = FE_CHEMISTRY_STREAM if _fe_group(code) == "II" else FE_PHYSICS_STREAM
        sem = 1 if _fe_group(code) == "I" else 2
        _assign_fe(db, divs, stream, sem, esh_faculty, fe_subjects)
        for i, g in enumerate(divs):
            prof = _make_profile(
                db, admin, f"Engineering Sciences & Humanities — {code} FE {g.name.split('-')[-1]}",
                ScopeType.DIVISION, sem, "Engineering Sciences & Humanities",
                _profile_rooms(esh_rooms, g.name.split('-')[-1]), esh_faculty, [g],
                [s for s in fe_subjects if s.semester == sem], "FE",
            )
            counts["profiles"] += 1

    # ── engineering branches: SE/TE/BE ────────────────────────
    for name, code, fe_group, fe_divs, se_divs, te_divs, be_divs, fe_strength in DEPARTMENTS:
        if code == "ES&H":
            continue
        fac = _make_faculty(db, name, code, FACULTY.get(code) or _synthetic_names(code, 16))
        counts["faculty"] += len(fac)
        rooms = _make_rooms(db, code, _rooms_for(code))
        counts["rooms"] += len(rooms)
        schemes = BRANCH_SCHEMES.get(code, {})
        subjects_by_sem = _make_subjects(db, name, [(sem, schemes.get(sem, [])) for sem in (3, 5, 7)], prefix=code)
        counts["subjects"] += len(subjects_by_sem)

        for year, sem in YEAR_SEMS.items():
            if year == 1:
                continue
            div_count = (se_divs if year == 2 else te_divs if year == 3 else be_divs)
            for div in "ABCD"[:div_count]:
                g = StudentGroup(
                    name=f"{code}-{'SE' if year==2 else 'TE' if year==3 else 'BE'}-{div}",
                    group_type=GroupType.DIVISION, department=name,
                    year=year, semester=sem, strength=60,
                )
                db.add(g)
                db.flush()
                counts["groups"] += 1
                subjs = [s for s in subjects_by_sem if s.semester == sem]
                _assign_branch(db, g, subjs, fac)
                prof = _make_profile(
                    db, admin, f"{name} — {'SE' if year==2 else 'TE' if year==3 else 'BE'}-{div}",
                    ScopeType.DIVISION, sem, name,
                    rooms, fac, [g], subjs,
                    "SE" if year == 2 else "TE" if year == 3 else "BE",
                )
                counts["profiles"] += 1

    db.commit()
    # Recompute honest counts straight from the DB (assignments are added deep
    # in the helper functions).
    from sqlalchemy import select, func as _f
    from app.models import TimetableProfile
    counts["faculty"] = db.scalar(_f.count(_f.distinct(Faculty.id))) or 0
    counts["groups"] = db.scalar(_f.count(_f.distinct(StudentGroup.id))) or 0
    counts["rooms"] = db.scalar(_f.count(_f.distinct(Room.id))) or 0
    counts["subjects"] = db.scalar(_f.count(_f.distinct(Subject.id))) or 0
    counts["assignments"] = db.scalar(_f.count(_f.distinct(SubjectAssignment.id))) or 0
    counts["profiles"] = db.scalar(_f.count(_f.distinct(TimetableProfile.id))) or 0
    return counts


def _fe_group(code: str) -> str:
    for name, c, g, *_ in DEPARTMENTS:
        if c == code:
            return g
    return "I"


def _make_faculty(db, dept_name: str, code: str, names: list[str]) -> list[Faculty]:
    local = code.lower().replace("&", "").replace("(", "").replace(")", "").replace("-", "")
    out = []
    for i, n in enumerate(names):
        f = Faculty(name=n, email=f"{local}.{i+1}@tcet.edu.in",
                    department=dept_name, max_hours_per_week=20, max_hours_per_day=6)
        db.add(f)
        out.append(f)
    db.flush()
    return out


def _make_rooms(db, code: str, specs) -> list[Room]:
    out = []
    for name, rtype, cap in specs:
        r = Room(name=name, room_code=name,
                 room_type=getattr(RoomType, rtype, RoomType.CLASSROOM),
                 capacity=cap, building="Main", floor=1,
                 has_projector=True, has_ac=True)
        db.add(r)
        out.append(r)
    db.flush()
    return out


def _profile_rooms(rooms: list[Room], div: str) -> list[Room]:
    # Assign a couple of classrooms + all labs; rooms are a shared pool.
    return rooms


def _make_subjects(db, dept_name: str, sems: list[tuple[int, list]], prefix: str) -> list[Subject]:
    out = []
    for sem, streams in sems:
        for (sname, code, kind, hours) in streams:
            reqs = _stream_spec(kind)
            s = Subject(
                name=sname, subject_code=f"{prefix}-S{sem}-{code}-{kind}",
                department=dept_name, semester=sem, hours_per_week=hours,
                requires_lab=(kind == "P"), requirements_json=reqs,
            )
            db.add(s)
            out.append(s)
    db.flush()
    return out


def _assign_fe(db, divs, stream, sem, faculty, subjects):
    """Assign the FE stream to each division; labs get 3 faculty (3 batches)."""
    fac_pool = list(faculty)
    fac_pool.sort(key=lambda f: f.id)
    subj_by_key = {(s.name, s.semester): s for s in subjects if s.semester == sem}
    for g in divs:
        for (sname, code, kind, hours) in stream:
            s = subj_by_key.get((sname, sem))
            if s is None:
                continue
            fac = fac_pool[(g.id + g.id) % len(fac_pool)]
            if kind == "P":
                # one assignment per batch, each with its own faculty
                for b in range(1, 4):
                    bfac = fac_pool[(g.id + g.id + b) % len(fac_pool)]
                    db.add(SubjectAssignment(
                        subject_id=s.id, faculty_id=bfac.id, group_id=g.id,
                        weekly_hours=hours, load_share=1.0, batch_number=b,
                    ))
            else:
                db.add(SubjectAssignment(
                    subject_id=s.id, faculty_id=fac.id, group_id=g.id,
                    weekly_hours=hours, load_share=1.0,
                ))


def _assign_branch(db, g, subjects, faculty):
    fac_pool = sorted(faculty, key=lambda f: f.id)
    for i, s in enumerate(subjects):
        fac = fac_pool[i % len(fac_pool)]
        if s.requirements_json and s.requirements_json.get("session_type") == "LAB":
            # SE/TE/BE labs run as 2 parallel batches (2 faculty).
            for b in range(1, 3):
                bfac = fac_pool[(i + b) % len(fac_pool)]
                db.add(SubjectAssignment(
                    subject_id=s.id, faculty_id=bfac.id, group_id=g.id,
                    weekly_hours=s.hours_per_week, load_share=1.0, batch_number=b,
                ))
        else:
            db.add(SubjectAssignment(
                subject_id=s.id, faculty_id=fac.id, group_id=g.id,
                weekly_hours=s.hours_per_week, load_share=1.0,
            ))


def _make_profile(db, admin, name, scope, sem, dept, rooms, faculty, groups,
                  subjects, grid_kind: str):
    prof = TimetableProfile(
        name=name, scope_type=scope, academic_year="2026-27", semester=sem,
        department=dept, created_by=admin.id,
    )
    db.add(prof)
    db.flush()
    for r in rooms:
        db.add(ProfileResource(profile_id=prof.id, resource_type=ResourceType.ROOM,
                               resource_id=r.id))
    for f in faculty:
        db.add(ProfileResource(profile_id=prof.id, resource_type=ResourceType.FACULTY,
                               resource_id=f.id))
    for g in groups:
        db.add(ProfileResource(profile_id=prof.id, resource_type=ResourceType.STUDENT_GROUP,
                               resource_id=g.id))
    for s in subjects:
        db.add(ProfileResource(profile_id=prof.id, resource_type=ResourceType.SUBJECT,
                               resource_id=s.id))
    if grid_kind == "FE":
        params = {
            "slots_per_day": ("9", ParamType.INT),
            "day_start_time": ("08:00", ParamType.STRING),
            "slot_duration_minutes": ("60", ParamType.INT),
            "lunch_break_after_slot": ("5", ParamType.INT),
            "lunch_break_duration_minutes": ("60", ParamType.INT),
            "working_days": ('["MON","TUE","WED","THU","FRI","SAT"]', ParamType.JSON),
            "term_start": ("2026-07-06", ParamType.STRING),
        }
    elif grid_kind == "BE":
        params = {
            "slots_per_day": ("8", ParamType.INT),
            "day_start_time": ("08:30", ParamType.STRING),
            "slot_duration_minutes": ("60", ParamType.INT),
            "lunch_break_after_slot": ("4", ParamType.INT),
            "lunch_break_duration_minutes": ("60", ParamType.INT),
            "working_days": ('["MON","TUE","WED","THU","FRI"]', ParamType.JSON),
            "term_start": ("2026-07-06", ParamType.STRING),
        }
    else:  # SE / TE
        params = {
            "slots_per_day": ("9", ParamType.INT),
            "day_start_time": ("08:30", ParamType.STRING),
            "slot_duration_minutes": ("60", ParamType.INT),
            "lunch_break_after_slot": ("4", ParamType.INT),
            "lunch_break_duration_minutes": ("60", ParamType.INT),
            "working_days": ('["MON","TUE","WED","THU","FRI","SAT"]', ParamType.JSON),
            "term_start": ("2026-07-06", ParamType.STRING),
        }
    for key, (value, ptype) in params.items():
        db.add(ProfileParameter(profile_id=prof.id, param_key=key, param_value=value,
                                param_type=ptype))
    # Labs are 2h blocks (real TCET practicals).
    db.add(HardConstraint(
        profile_id=prof.id, constraint_type="CONTIGUOUS_LAB_SLOTS",
        config_json={"default_block_length": 2},
        description="2h lab blocks (real TCET practicals)",
    ))
    # Real college rule: at most one practical subject per day.
    db.add(HardConstraint(
        profile_id=prof.id, constraint_type="MAX_ONE_LAB_PER_DAY",
        config_json={}, description="max one practical subject per day",
    ))
    return prof


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wipe", action="store_true",
                        help="truncate all scheduling tables before seeding")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.wipe:
            print("wiping scheduling tables…")
            wipe(db)
        counts = seed(db)
        print("seed complete:")
        for k, v in counts.items():
            print(f"  {k:>12}: {v}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
