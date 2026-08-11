"""Phase 2 tests: EXAM_DATE_SEPARATION registry rule (exam domain).

Exams reuse the weekly-template engine. A profile whose ``session_type``
parameter is ``"EXAM"`` runs in exam mode: every subject-assignment expands to
exactly ONE ``SessionType.EXAM`` session, and the registry rule rejects any
placement whose materialized ``slot_date`` is closer than ``min_days`` to
another exam of the same group. Because an exam timetable is a separate
generation for a subset of groups, one branch/year can be on exams while the
rest keep their published class timetable — the published-conflict loader
exempts the examing groups' own class slots (classes suspended) while every
other branch's rooms/faculty stay reserved.
"""
from datetime import time

from app.tests.test_runner import suite, test
from app.engine.constraint_checker import SlotCandidate


def _seed_exam_subjects(n_subjects, *, term_start="2025-01-06", scope_exam=False):
    """One group, one teacher, one room, ``n_subjects`` exams, exam profile.

    The profile carries ``session_type=EXAM`` (or ``scope_type=EXAM`` when
    ``scope_exam=True``, which the engine treats as an implicit exam mode) and
    (optionally) ``term_start``; each subject has a 1-hour assignment so exam
    mode produces one exam per subject. Returns ids including the subject list.
    """
    from app.tests.test_runner import (reset_db, ensure_settings, create_admin,
                                       TestingSessionLocal)
    reset_db()
    ensure_settings({"enable_soft_constraint_scoring": False})
    create_admin()
    db = TestingSessionLocal()
    try:
        from app.models.admin import Admin as AdminModel
        from app.models.faculty import Faculty
        from app.models.groups import StudentGroup, GroupType
        from app.models.rooms import Room, RoomType
        from app.models.subjects import Subject
        from app.models.profiles import (
            TimetableProfile, ProfileResource, ProfileParameter, ParamType,
            ResourceType, ScopeType,
        )
        from app.models.subject_assignments import SubjectAssignment

        admin = db.query(AdminModel).first()
        fac = Faculty(name="Alice", email="alice@exam.test", department="CS")
        db.add(fac); db.flush()
        grp = StudentGroup(name="CS-A", group_type=GroupType.DIVISION,
                           department="CS", year=2, semester=3, strength=60)
        db.add(grp); db.flush()
        room = Room(name="R1", room_code="R1", room_type=RoomType.CLASSROOM,
                    capacity=80, building="A")
        db.add(room); db.flush()

        subjects = []
        for i in range(n_subjects):
            s = Subject(name=f"Subject {i}", subject_code=f"EX{i:03d}",
                        department="CS", semester=3, hours_per_week=1,
                        requires_lab=False)
            db.add(s); db.flush()
            subjects.append(s)

        prof = TimetableProfile(
            name="Exam profile",
            scope_type=ScopeType.EXAM if scope_exam else ScopeType.DIVISION,
            academic_year="2025-26", semester=3,
            department="CS", created_by=admin.id)
        db.add(prof); db.flush()

        db.add(ProfileResource(profile_id=prof.id, resource_type=ResourceType.ROOM,
                               resource_id=room.id))
        db.add(ProfileResource(profile_id=prof.id, resource_type=ResourceType.FACULTY,
                               resource_id=fac.id))
        db.add(ProfileResource(profile_id=prof.id,
                               resource_type=ResourceType.STUDENT_GROUP,
                               resource_id=grp.id))
        for s in subjects:
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.SUBJECT,
                                   resource_id=s.id))
            db.add(SubjectAssignment(subject_id=s.id, faculty_id=fac.id,
                                     group_id=grp.id, weekly_hours=1,
                                     load_share=1.0))
        db.add(ProfileParameter(profile_id=prof.id, param_key="slots_per_day",
                                param_value="5", param_type=ParamType.INT))
        db.add(ProfileParameter(profile_id=prof.id, param_key="working_days",
                                param_value='["MON","TUE","WED","THU","FRI"]',
                                param_type=ParamType.JSON))
        if not scope_exam:
            db.add(ProfileParameter(profile_id=prof.id, param_key="session_type",
                                    param_value="EXAM", param_type=ParamType.STRING))
        if term_start:
            db.add(ProfileParameter(profile_id=prof.id, param_key="term_start",
                                    param_value=term_start,
                                    param_type=ParamType.STRING))
        db.commit()
        return {"faculty": fac.id, "group": grp.id, "room": room.id,
                "profile": prof.id, "subjects": [s.id for s in subjects],
                "admin": admin.id}
    finally:
        db.close()


@suite("Phase 2 — EXAM_DATE_SEPARATION registry rule")
def _phase2_exam_date_separation(s):
    def _gen_slots(client, headers, profile_id, algorithm="GREEDY"):
        r = client.post("/generate/", headers=headers, json={
            "profile_id": profile_id, "academic_year": "2025-26", "semester": 3,
            "timetable_type": "EXAM", "instances_requested": 1, "algorithm": algorithm,
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        inst_id = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]["id"]
        return client.get(f"/instances/{inst_id}/slots", headers=headers).json()

    def _add_rule(client, headers, profile_id, min_days):
        r = client.post("/constraints/hard", headers=headers, json={
            "profile_id": profile_id,
            "constraint_type": "EXAM_DATE_SEPARATION",
            "config_json": {"min_days": min_days},
        })
        assert r.status_code == 201, r.text

    def _cand(session_type="EXAM", slot_date=None, group_id=1, subject_id=1):
        return SlotCandidate(
            instance_id=1, day_of_week=0, slot_number=1,
            start_time=time(9), end_time=time(10), faculty_id=1, room_id=1,
            student_group_id=group_id, subject_id=subject_id,
            session_type=session_type, slot_date=slot_date,
        )

    @test("_exam_date_separation enforces a minimum gap between a group's exams")
    def t_validator(client):
        from datetime import date
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY

        class _Slot:
            def __init__(self, stype, gid, d):
                self.session_type, self.student_group_id, self.slot_date = stype, gid, d

        v = HARD_CONSTRAINT_REGISTRY["EXAM_DATE_SEPARATION"]
        d = date(2025, 1, 6)  # Monday
        # One committed exam on Mon; a Tuesday exam is 1 day apart (too close
        # for min_days=2), Wednesday is 2 days apart (exactly the minimum).
        committed = [_Slot("EXAM", 1, d)]
        assert v(_cand(slot_date=date(2025, 1, 7)), committed,
                 {"min_days": 2}, None) is not None
        assert v(_cand(slot_date=date(2025, 1, 8)), committed,
                 {"min_days": 2}, None) is None
        # Same-day is the tightest case and always rejected for min_days >= 1.
        assert v(_cand(slot_date=d), committed, {"min_days": 1}, None) is not None
        # No committed exams -> always acceptable.
        assert v(_cand(slot_date=date(2025, 1, 7)), [], {"min_days": 2}, None) is None

    @test("_exam_date_separation only governs EXAM sessions with a date")
    def t_scope(client):
        from datetime import date
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY

        class _Slot:
            def __init__(self, stype, gid, d):
                self.session_type, self.student_group_id, self.slot_date = stype, gid, d

        v = HARD_CONSTRAINT_REGISTRY["EXAM_DATE_SEPARATION"]
        d = date(2025, 1, 6)
        committed = [_Slot("EXAM", 1, d)]
        # A LECTURE candidate is never governed even on a clash day.
        assert v(_cand("LECTURE", d), committed, {"min_days": 2}, None) is None
        # A date-less candidate (no term_start anchor) is a no-op.
        assert v(_cand("EXAM", None), committed, {"min_days": 2}, None) is None
        # Committed slots without a date cannot collide.
        assert v(_cand("EXAM", d), [_Slot("EXAM", 1, None)],
                 {"min_days": 2}, None) is None
        # Different groups never collide.
        assert v(_cand("EXAM", d, group_id=2), committed,
                 {"min_days": 2}, None) is None
        # group_id scoping narrows the rule to one group.
        cfg = {"min_days": 2, "group_id": 1}
        assert v(_cand("EXAM", d, group_id=2), committed, cfg, None) is None
        assert v(_cand("EXAM", d, group_id=1), committed, cfg, None) is not None
        # Missing or zero min_days makes the rule inert.
        assert v(_cand("EXAM", d), committed, {}, None) is None
        assert v(_cand("EXAM", d), committed, {"min_days": 0}, None) is None

    @test("exam mode schedules one EXAM session per subject (greedy)")
    def t_exam_mode_greedy(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = _seed_exam_subjects(4)
        headers = auth_headers(login_token(client))
        slots = _gen_slots(client, headers, ids["profile"])
        assert len(slots) == 4, f"one exam per subject expected, got {len(slots)}"
        assert all(sl["session_type"] == "EXAM" for sl in slots), slots
        assert len({sl["subject_id"] for sl in slots}) == 4, slots

    @test("scope_type=EXAM implies exam mode without the session_type param")
    def t_exam_mode_by_scope(client):
        from app.tests.test_runner import login_token, auth_headers
        # scope_exam=True: no session_type param, the scope alone flips exam mode.
        ids = _seed_exam_subjects(4, scope_exam=True)
        headers = auth_headers(login_token(client))
        slots = _gen_slots(client, headers, ids["profile"])
        assert len(slots) == 4, f"one exam per subject expected, got {len(slots)}"
        assert all(sl["session_type"] == "EXAM" for sl in slots), slots

    @test("EXAM_DATE_SEPARATION spaces a group's exams by min_days (greedy)")
    def t_separation_greedy(client):
        from datetime import date
        from app.tests.test_runner import login_token, auth_headers
        ids = _seed_exam_subjects(5)
        headers = auth_headers(login_token(client))
        _add_rule(client, headers, ids["profile"], 2)
        slots = _gen_slots(client, headers, ids["profile"])
        dates = sorted(date.fromisoformat(sl["slot_date"]) for sl in slots)
        # A 5-day week can hold at most 3 exams at >= 2-day spacing (Mon/Wed/Fri).
        assert len(slots) == 3, f"expected 3 spaced exams, got {len(slots)}"
        for earlier, later in zip(dates, dates[1:]):
            assert (later - earlier).days >= 2, (dates, slots)
        assert all(sl["session_type"] == "EXAM" for sl in slots), slots

    @test("EXAM_DATE_SEPARATION is inert without a term_start anchor")
    def t_no_anchor(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = _seed_exam_subjects(4, term_start=None)
        headers = auth_headers(login_token(client))
        _add_rule(client, headers, ids["profile"], 2)
        slots = _gen_slots(client, headers, ids["profile"])
        # No materialized dates -> the rule cannot fire; all 4 exams land.
        assert len(slots) == 4, slots
        assert all(sl["slot_date"] is None for sl in slots), slots

    @test("exam mode schedules one EXAM session per subject (OR-Tools)")
    def t_exam_mode_ortools(client):
        from datetime import date
        from app.tests.test_runner import login_token, auth_headers
        ids = _seed_exam_subjects(4)
        headers = auth_headers(login_token(client))
        _add_rule(client, headers, ids["profile"], 1)
        slots = _gen_slots(client, headers, ids["profile"], algorithm="OR_TOOLS")
        assert len(slots) == 4, f"expected 4 exams, got {len(slots)}"
        dates = sorted(date.fromisoformat(sl["slot_date"]) for sl in slots)
        for earlier, later in zip(dates, dates[1:]):
            assert (later - earlier).days >= 1, (dates, slots)
        assert all(sl["session_type"] == "EXAM" for sl in slots), slots

    @test("_load_published_conflicts exempts examing groups' own slots")
    def t_exempt_groups(client):
        from datetime import date
        from app.tests.conftest import TestingSessionLocal
        from app.engine.scheduler import Scheduler
        from app.models.generation import (TimetableInstance, TimetableSlot,
                                           SessionType, InstanceStatus)

        def _seed_slots():
            reset_db_slots = _seed_exam_subjects(1)
            db = TestingSessionLocal()
            try:
                inst = TimetableInstance(generation_id=1, instance_number=1,
                                         status=InstanceStatus.PUBLISHED)
                db.add(inst); db.flush()
                g_a = reset_db_slots["group"]
                g_b = g_a + 100
                db.add_all([
                    TimetableSlot(instance_id=inst.id, slot_date=date(2025, 1, 6),
                                  day_of_week=0, slot_number=1,
                                  start_time=time(9), end_time=time(10),
                                  faculty_id=reset_db_slots["faculty"],
                                  room_id=reset_db_slots["room"],
                                  student_group_id=g_a,
                                  session_type=SessionType.LECTURE),
                    TimetableSlot(instance_id=inst.id, slot_date=date(2025, 1, 6),
                                  day_of_week=0, slot_number=1,
                                  start_time=time(9), end_time=time(10),
                                  faculty_id=99, room_id=98,
                                  student_group_id=g_b,
                                  session_type=SessionType.LECTURE),
                ])
                db.commit()
                return g_a, g_b
            finally:
                db.close()

        g_a, g_b = _seed_slots()
        db = TestingSessionLocal()
        try:
            scheduler = Scheduler(db)
            full = scheduler._load_published_conflicts()
            assert (g_a, 0, 1) in full["group"], full
            assert (g_b, 0, 1) in full["group"], full
            exempt = scheduler._load_published_conflicts(exempt_groups={g_a})
            # Group A's own class slot is freed everywhere; group B's stays.
            assert (g_a, 0, 1) not in exempt["group"], exempt
            assert (g_b, 0, 1) in exempt["group"], exempt
            assert (exempt["room"] == {(98, 0, 1)}), exempt
            assert (exempt["faculty"] == {(99, 0, 1)}), exempt
        finally:
            db.close()

    @test("an exam timetable coexists with other branches' published classes")
    def t_mixed_branches(client):
        from app.tests.test_runner import (reset_db, ensure_settings,
                                           create_admin, login_token, auth_headers,
                                           TestingSessionLocal)
        from app.models.groups import StudentGroup, GroupType
        from app.models.faculty import Faculty
        from app.models.rooms import Room, RoomType
        from app.models.subjects import Subject
        from app.models.profiles import (ProfileResource, ProfileParameter,
                                         ParamType, ResourceType, ScopeType,
                                         TimetableProfile)
        from app.models.subject_assignments import SubjectAssignment
        from app.models.admin import Admin as AdminModel

        reset_db()
        ensure_settings({"enable_soft_constraint_scoring": False})
        create_admin()
        token = login_token(client)
        headers = auth_headers(token)
        db = TestingSessionLocal()
        try:
            admin = db.query(AdminModel).first()
            # Branch A (will take exams) and branch B (keeps teaching).
            fac_a = Faculty(name="Prof A", email="a@branch.test", department="CS")
            fac_b = Faculty(name="Prof B", email="b@branch.test", department="CS")
            db.add_all([fac_a, fac_b]); db.flush()
            grp_a = StudentGroup(name="CS-A", group_type=GroupType.DIVISION,
                                 department="CS", year=2, semester=3, strength=60)
            grp_b = StudentGroup(name="CS-B", group_type=GroupType.DIVISION,
                                 department="CS", year=3, semester=5, strength=60)
            db.add_all([grp_a, grp_b]); db.flush()
            room_a = Room(name="RA", room_code="RA", room_type=RoomType.CLASSROOM,
                          capacity=80, building="A")
            room_b = Room(name="RB", room_code="RB", room_type=RoomType.CLASSROOM,
                          capacity=80, building="A")
            db.add_all([room_a, room_b]); db.flush()
            subj_a1 = Subject(name="A-1", subject_code="A1", department="CS",
                              semester=3, hours_per_week=1, requires_lab=False)
            subj_a2 = Subject(name="A-2", subject_code="A2", department="CS",
                              semester=3, hours_per_week=1, requires_lab=False)
            subj_b = Subject(name="B-1", subject_code="B1", department="CS",
                             semester=5, hours_per_week=1, requires_lab=False)
            db.add_all([subj_a1, subj_a2, subj_b]); db.flush()

            # CLASS profile: everything, so one published timetable covers both.
            class_prof = TimetableProfile(name="Whole college",
                                          scope_type=ScopeType.DEPARTMENT,
                                          academic_year="2025-26", semester=3,
                                          department="CS", created_by=admin.id)
            db.add(class_prof); db.flush()
            for rid in (room_a.id, room_b.id):
                db.add(ProfileResource(profile_id=class_prof.id,
                                       resource_type=ResourceType.ROOM, resource_id=rid))
            for fid in (fac_a.id, fac_b.id):
                db.add(ProfileResource(profile_id=class_prof.id,
                                       resource_type=ResourceType.FACULTY, resource_id=fid))
            for gid in (grp_a.id, grp_b.id):
                db.add(ProfileResource(profile_id=class_prof.id,
                                       resource_type=ResourceType.STUDENT_GROUP, resource_id=gid))
            for sid in (subj_a1.id, subj_a2.id, subj_b.id):
                db.add(ProfileResource(profile_id=class_prof.id,
                                       resource_type=ResourceType.SUBJECT, resource_id=sid))
            db.add(ProfileParameter(profile_id=class_prof.id, param_key="slots_per_day",
                                    param_value="5", param_type=ParamType.INT))
            db.add(ProfileParameter(profile_id=class_prof.id, param_key="working_days",
                                    param_value='["MON","TUE","WED","THU","FRI"]',
                                    param_type=ParamType.JSON))
            db.add(SubjectAssignment(subject_id=subj_a1.id, faculty_id=fac_a.id,
                                     group_id=grp_a.id, weekly_hours=1, load_share=1.0))
            db.add(SubjectAssignment(subject_id=subj_a2.id, faculty_id=fac_a.id,
                                     group_id=grp_a.id, weekly_hours=1, load_share=1.0))
            db.add(SubjectAssignment(subject_id=subj_b.id, faculty_id=fac_b.id,
                                     group_id=grp_b.id, weekly_hours=1, load_share=1.0))

            # EXAM profile: only branch A, with BOTH rooms so the solver can
            # (wrongly) reach for branch B's room and must be stopped.
            exam_prof = TimetableProfile(name="CS-A exams", scope_type=ScopeType.DIVISION,
                                         academic_year="2025-26", semester=3,
                                         department="CS", created_by=admin.id)
            db.add(exam_prof); db.flush()
            for rid in (room_a.id, room_b.id):
                db.add(ProfileResource(profile_id=exam_prof.id,
                                       resource_type=ResourceType.ROOM, resource_id=rid))
            db.add(ProfileResource(profile_id=exam_prof.id,
                                   resource_type=ResourceType.FACULTY, resource_id=fac_a.id))
            db.add(ProfileResource(profile_id=exam_prof.id,
                                   resource_type=ResourceType.STUDENT_GROUP, resource_id=grp_a.id))
            for sid in (subj_a1.id, subj_a2.id):
                db.add(ProfileResource(profile_id=exam_prof.id,
                                       resource_type=ResourceType.SUBJECT, resource_id=sid))
            db.add(ProfileParameter(profile_id=exam_prof.id, param_key="slots_per_day",
                                    param_value="5", param_type=ParamType.INT))
            db.add(ProfileParameter(profile_id=exam_prof.id, param_key="working_days",
                                    param_value='["MON","TUE","WED","THU","FRI"]',
                                    param_type=ParamType.JSON))
            db.add(ProfileParameter(profile_id=exam_prof.id, param_key="session_type",
                                    param_value="EXAM", param_type=ParamType.STRING))
            db.add(ProfileParameter(profile_id=exam_prof.id, param_key="term_start",
                                    param_value="2025-01-06", param_type=ParamType.STRING))
            db.commit()
            ids = {"class_prof": class_prof.id, "exam_prof": exam_prof.id,
                   "group_b": grp_b.id}
        finally:
            db.close()

        # Publish a CLASS timetable covering both branches.
        r = client.post("/generate/", headers=headers, json={
            "profile_id": ids["class_prof"], "academic_year": "2025-26",
            "semester": 3, "timetable_type": "CLASS",
            "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        class_gen = r.json()
        class_inst = client.get(
            f"/instances/{class_gen['id']}", headers=headers).json()[0]["id"]
        class_slots = client.get(
            f"/instances/{class_inst}/slots", headers=headers).json()
        assert len(class_slots) == 3, class_slots
        r = client.post(f"/instances/{class_inst}/publish", headers=headers)
        assert r.status_code == 200, r.text

        # Branch B's published class bookings must be untouchable.
        b_reserved = {
            (sl["room_id"], sl["day_of_week"], sl["slot_number"])
            for sl in class_slots if sl["student_group_id"] == ids["group_b"]
        }
        b_faculty = {
            (sl["faculty_id"], sl["day_of_week"], sl["slot_number"])
            for sl in class_slots if sl["student_group_id"] == ids["group_b"]
        }
        assert b_reserved and b_faculty, class_slots

        # Run the exam timetable for branch A while branch B keeps teaching.
        _add_rule(client, headers, ids["exam_prof"], 1)
        exam_slots = _gen_slots(client, headers, ids["exam_prof"])
        assert len(exam_slots) == 2, f"expected 2 exams, got {len(exam_slots)}"
        assert all(sl["session_type"] == "EXAM" for sl in exam_slots), exam_slots
        assert all(sl["student_group_id"] != ids["group_b"] for sl in exam_slots)
        # No exam may reuse branch B's room or teacher at branch B's class time.
        exam_rooms = {(sl["room_id"], sl["day_of_week"], sl["slot_number"])
                      for sl in exam_slots}
        exam_faculty = {(sl["faculty_id"], sl["day_of_week"], sl["slot_number"])
                        for sl in exam_slots}
        assert exam_rooms.isdisjoint(b_reserved), (
            f"exam used branch B's class room: {exam_rooms & b_reserved}"
        )
        assert exam_faculty.isdisjoint(b_faculty), (
            f"exam used branch B's teacher: {exam_faculty & b_faculty}"
        )

    return [t_validator, t_scope, t_exam_mode_greedy, t_exam_mode_by_scope,
            t_separation_greedy, t_no_anchor, t_exam_mode_ortools,
            t_exempt_groups, t_mixed_branches]
