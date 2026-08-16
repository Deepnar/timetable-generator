"""Custom test runner — no pytest required.

Usage:
    uv run python -m app.tests

Tests register themselves by calling :func:`suite` and :func:`test`:

    @suite("My group")
    def _(s):
        @test("does the thing")
        def _(client):
            assert client.get("/health").status_code == 200
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable, List

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))

# The conftest must run BEFORE any other app code so the in-memory
# engine is in place and the get_db override is wired.
import app.tests.conftest as conftest  # noqa: F401, E402
from app.tests.conftest import (  # noqa: E402
    reset_db,
    make_client,
    create_admin,
    login_token,
    auth_headers,
    ensure_settings,
    TestingSessionLocal,
)


@dataclass
class _Suite:
    name: str
    tests: List[Callable] = field(default_factory=list)


SUITES: list[_Suite] = []


def suite(name: str) -> Callable:
    """Wrap a function that registers tests. All test callables returned
    by the wrapped function are appended to the suite.

    The trick: we just iterate over the function's return values. Tests
    should be returned in the order they should run.
    """
    s = _Suite(name=name)
    SUITES.append(s)

    def deco(register: Callable) -> Callable:
        # Allow either: returns list of tests, OR adds them via .add
        result = register(s)
        if result is not None:
            for fn in result:
                if callable(fn) and getattr(fn, "__test__", False):
                    s.tests.append(fn)
        return register

    return deco


def test(name: str) -> Callable:
    """Mark a function as a test with the given human-readable name.

    The wrapped function must accept a single ``TestClient`` argument.
    """

    def deco(fn: Callable) -> Callable:
        fn.__test_name__ = name
        fn.__test__ = True
        return fn

    return deco


def run() -> int:
    total = passed = failed = 0
    print()
    for s in SUITES:
        print(f"=== {s.name} ===")
        for fn in s.tests:
            total += 1
            t0 = time.time()
            try:
                fn(make_client())
                dt = (time.time() - t0) * 1000
                passed += 1
                print(f"  ✓ {fn.__test_name__} ({dt:.1f} ms)")
            except AssertionError as e:
                dt = (time.time() - t0) * 1000
                failed += 1
                print(f"  ✗ {fn.__test_name__} ({dt:.1f} ms): {e}")
            except Exception as e:  # noqa: BLE001
                dt = (time.time() - t0) * 1000
                failed += 1
                tb = traceback.format_exc()
                print(f"  💥 {fn.__test_name__} ({dt:.1f} ms): {e}\n{tb}")

    print(f"\n=== {passed}/{total} passed, {failed} failed ===")
    return 0 if failed == 0 else 1


# ── helper: build a base scenario with admin + profile + room + group + faculty + subject ──
def seed_minimal(
    *,
    allow_cross_dept: bool = False,
    enable_lab_batches: bool = False,
    cross_dept: bool = False,
    faculty_max_per_week: int | None = None,
    faculty_max_per_day: int | None = None,
    requires_lab: bool = False,
    weekly_hours: int = 3,
):
    """Insert one of each resource and a subject assignment.

    ``requires_lab`` marks the subject as a lab (so generation uses the lab
    room and lab block rules can apply); ``weekly_hours`` controls the
    assignment's load. Returns a dict of IDs so the test can build more on top.
    """
    reset_db()
    ensure_settings({
        "enable_lab_batches": enable_lab_batches,
        "allow_cross_dept_subjects": allow_cross_dept,
        "enable_soft_constraint_scoring": True,
    })
    create_admin()
    db = TestingSessionLocal()
    try:
        from app.models.faculty import Faculty
        from app.models.groups import StudentGroup, GroupType
        from app.models.rooms import Room, RoomType
        from app.models.subjects import Subject
        from app.models.profiles import (
            TimetableProfile, ProfileResource, ProfileParameter, ParamType,
            ResourceType, ScopeType,
        )
        from app.models.subject_assignments import SubjectAssignment
        from app.models.admin import Admin as AdminModel

        admin = db.query(AdminModel).first()

        fac = Faculty(name="Alice", email="alice@x.com", department="CS")
        if faculty_max_per_week is not None:
            fac.max_hours_per_week = faculty_max_per_week
        if faculty_max_per_day is not None:
            fac.max_hours_per_day = faculty_max_per_day
        db.add(fac); db.flush()
        # For a genuine cross-department scenario the group and the subject must
        # live in DIFFERENT departments. Keep the group in CS and (below) move
        # only the subject to MATH when cross_dept is requested. A lab subject
        # must fit the lab room's capacity, so the group is sized accordingly.
        grp = StudentGroup(
            name="CS-A", group_type=GroupType.DIVISION,
            department="CS", year=2, semester=3, strength=40 if requires_lab else 60,
        )
        db.add(grp); db.flush()
        classroom = Room(
            name="R1", room_code="R1", room_type=RoomType.CLASSROOM,
            capacity=80, building="A",
        )
        lab = Room(
            name="L1", room_code="L1", room_type=RoomType.LAB,
            capacity=40, building="A",
        )
        db.add_all([classroom, lab]); db.flush()
        subj = Subject(
            name="Maths", subject_code="M101",
            department="MATH" if cross_dept else "CS",
            semester=3, hours_per_week=weekly_hours, requires_lab=requires_lab,
        )
        db.add(subj); db.flush()

        prof = TimetableProfile(
            name="Test profile",
            scope_type=ScopeType.DIVISION,
            academic_year="2025-26",
            semester=3, department="CS", created_by=admin.id,
        )
        db.add(prof); db.flush()

        for rid in (classroom.id, lab.id):
            db.add(ProfileResource(
                profile_id=prof.id, resource_type=ResourceType.ROOM,
                resource_id=rid,
            ))
        db.add(ProfileResource(
            profile_id=prof.id, resource_type=ResourceType.FACULTY,
            resource_id=fac.id,
        ))
        db.add(ProfileResource(
            profile_id=prof.id, resource_type=ResourceType.STUDENT_GROUP,
            resource_id=grp.id,
        ))
        db.add(ProfileResource(
            profile_id=prof.id, resource_type=ResourceType.SUBJECT,
            resource_id=subj.id,
        ))
        db.add(ProfileParameter(
            profile_id=prof.id, param_key="slots_per_day",
            param_value="5", param_type=ParamType.INT,
        ))
        db.add(ProfileParameter(
            profile_id=prof.id, param_key="working_days",
            param_value='["MON","TUE","WED","THU","FRI"]',
            param_type=ParamType.JSON,
        ))

        db.add(SubjectAssignment(
            subject_id=subj.id, faculty_id=fac.id, group_id=grp.id,
            weekly_hours=weekly_hours, load_share=1.0,
        ))
        # College-default institutional constraint rows, mirroring migration
        # c9d4e8f2a6b0 (Phase 3b, A10): institutional policy fires only from a
        # row, so the base scenario carries the same defaults a migrated DB
        # has. Tests that want the rules OFF delete these rows.
        from app.models.constraints import HardConstraint as _HC
        from app.engine.constraint_registry import DEFAULT_INSTITUTIONAL_CONFIGS
        for rule_type, config in DEFAULT_INSTITUTIONAL_CONFIGS.items():
            db.add(_HC(profile_id=None, constraint_type=rule_type,
                       config_json=dict(config)))
        db.commit()
        return {
            "faculty": fac.id, "group": grp.id, "classroom": classroom.id,
            "lab": lab.id, "subject": subj.id, "profile": prof.id,
            "admin": admin.id,
        }
    finally:
        db.close()


def seed_two_divisions():
    """Two divisions (different years), two teachers, two subjects.

    Used by the export-filter tests so filters actually narrow the result.
    Returns a dict of ids; generation yields 2 sessions per division.
    """
    reset_db()
    ensure_settings({"enable_soft_constraint_scoring": False})
    create_admin()
    db = TestingSessionLocal()
    try:
        from app.models.faculty import Faculty
        from app.models.groups import StudentGroup, GroupType
        from app.models.rooms import Room, RoomType
        from app.models.subjects import Subject
        from app.models.profiles import (
            TimetableProfile, ProfileResource, ProfileParameter, ParamType,
            ResourceType, ScopeType,
        )
        from app.models.subject_assignments import SubjectAssignment
        from app.models.admin import Admin as AdminModel

        admin = db.query(AdminModel).first()

        fac_a = Faculty(name="Prof A", email="a@x.com", department="CS")
        fac_b = Faculty(name="Prof B", email="b@x.com", department="CS")
        db.add_all([fac_a, fac_b]); db.flush()

        grp_a = StudentGroup(name="CS-A", group_type=GroupType.DIVISION,
                             department="CS", year=2, semester=3, strength=60)
        grp_b = StudentGroup(name="CS-B", group_type=GroupType.DIVISION,
                             department="CS", year=3, semester=5, strength=60)
        db.add_all([grp_a, grp_b]); db.flush()

        room1 = Room(name="R1", room_code="R1", room_type=RoomType.CLASSROOM,
                     capacity=80, building="A")
        room2 = Room(name="R2", room_code="R2", room_type=RoomType.CLASSROOM,
                     capacity=80, building="A")
        db.add_all([room1, room2]); db.flush()

        subj_a = Subject(name="Algorithms", subject_code="CS-A1", department="CS",
                         semester=3, hours_per_week=2, requires_lab=False)
        subj_b = Subject(name="Networks", subject_code="CS-B1", department="CS",
                         semester=5, hours_per_week=2, requires_lab=False)
        db.add_all([subj_a, subj_b]); db.flush()

        prof = TimetableProfile(name="Dept", scope_type=ScopeType.DEPARTMENT,
                                academic_year="2025-26", semester=3,
                                department="CS", created_by=admin.id)
        db.add(prof); db.flush()

        for rid in (room1.id, room2.id):
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.ROOM, resource_id=rid))
        for fid in (fac_a.id, fac_b.id):
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.FACULTY, resource_id=fid))
        for gid in (grp_a.id, grp_b.id):
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.STUDENT_GROUP, resource_id=gid))
        for sid in (subj_a.id, subj_b.id):
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.SUBJECT, resource_id=sid))
        db.add(ProfileParameter(profile_id=prof.id, param_key="slots_per_day",
                                param_value="6", param_type=ParamType.INT))
        db.add(ProfileParameter(profile_id=prof.id, param_key="working_days",
                                param_value='["MON","TUE","WED","THU","FRI"]',
                                param_type=ParamType.JSON))

        db.add(SubjectAssignment(subject_id=subj_a.id, faculty_id=fac_a.id,
                                 group_id=grp_a.id, weekly_hours=2, load_share=1.0))
        db.add(SubjectAssignment(subject_id=subj_b.id, faculty_id=fac_b.id,
                                 group_id=grp_b.id, weekly_hours=2, load_share=1.0))
        db.commit()
        return {
            "profile": prof.id, "group_a": grp_a.id, "group_b": grp_b.id,
            "faculty_a": fac_a.id, "faculty_b": fac_b.id,
            "subject_a": subj_a.id, "subject_b": subj_b.id, "admin": admin.id,
        }
    finally:
        db.close()


def seed_two_profiles():
    """Two independent profiles, each with its own faculty/group/room/subject.

    Used by the profile-combination tests: combining them must merge every
    resource so one generation schedules both, parameters must merge with the
    higher-weight member winning collisions, and each member's constraints must
    carry through. Returns ids for both profiles and their resources.
    """
    reset_db()
    ensure_settings({"enable_soft_constraint_scoring": False})
    create_admin()
    db = TestingSessionLocal()
    try:
        from app.models.faculty import Faculty
        from app.models.groups import StudentGroup, GroupType
        from app.models.rooms import Room, RoomType
        from app.models.subjects import Subject
        from app.models.profiles import (
            TimetableProfile, ProfileResource, ProfileParameter, ParamType,
            ResourceType, ScopeType,
        )
        from app.models.subject_assignments import SubjectAssignment
        from app.models.admin import Admin as AdminModel

        admin = db.query(AdminModel).first()

        fac_a = Faculty(name="Alice", email="alice@combine.test", department="CS")
        fac_b = Faculty(name="Bob", email="bob@combine.test", department="CS")
        grp_a = StudentGroup(name="CS-A", group_type=GroupType.DIVISION,
                             department="CS", year=2, semester=3, strength=60)
        grp_b = StudentGroup(name="CS-B", group_type=GroupType.DIVISION,
                             department="CS", year=3, semester=5, strength=60)
        room_a = Room(name="R1", room_code="R1", room_type=RoomType.CLASSROOM,
                      capacity=80, building="A")
        room_b = Room(name="R2", room_code="R2", room_type=RoomType.CLASSROOM,
                      capacity=80, building="A")
        subj_a = Subject(name="Maths", subject_code="M101", department="CS",
                         semester=3, hours_per_week=3, requires_lab=False)
        subj_b = Subject(name="Physics", subject_code="PH101", department="CS",
                         semester=5, hours_per_week=3, requires_lab=False)
        prof_a = TimetableProfile(name="Profile A", scope_type=ScopeType.DIVISION,
                                  academic_year="2025-26", semester=3,
                                  department="CS", created_by=admin.id)
        prof_b = TimetableProfile(name="Profile B", scope_type=ScopeType.DIVISION,
                                  academic_year="2025-26", semester=5,
                                  department="CS", created_by=admin.id)
        db.add_all([fac_a, fac_b, grp_a, grp_b, room_a, room_b, subj_a, subj_b,
                    prof_a, prof_b])
        db.flush()

        def _attach(prof, room, fac, grp, subj):
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.ROOM, resource_id=room.id))
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.FACULTY, resource_id=fac.id))
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.STUDENT_GROUP, resource_id=grp.id))
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.SUBJECT, resource_id=subj.id))
            db.add(ProfileParameter(profile_id=prof.id, param_key="slots_per_day",
                                    param_value="5", param_type=ParamType.INT))
            db.add(ProfileParameter(profile_id=prof.id, param_key="working_days",
                                    param_value='["MON","TUE","WED","THU","FRI"]',
                                    param_type=ParamType.JSON))

        _attach(prof_a, room_a, fac_a, grp_a, subj_a)
        _attach(prof_b, room_b, fac_b, grp_b, subj_b)

        db.add(SubjectAssignment(subject_id=subj_a.id, faculty_id=fac_a.id,
                                 group_id=grp_a.id, weekly_hours=3, load_share=1.0))
        db.add(SubjectAssignment(subject_id=subj_b.id, faculty_id=fac_b.id,
                                 group_id=grp_b.id, weekly_hours=3, load_share=1.0))
        db.commit()
        return {
            "profile_a": prof_a.id, "profile_b": prof_b.id,
            "faculty_a": fac_a.id, "faculty_b": fac_b.id,
            "group_a": grp_a.id, "group_b": grp_b.id,
            "room_a": room_a.id, "room_b": room_b.id,
            "subject_a": subj_a.id, "subject_b": subj_b.id,
        }
    finally:
        db.close()
