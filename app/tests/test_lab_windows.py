"""Lab windows (A1): one division splits into batches that do DIFFERENT
subjects simultaneously, rotating week to week.

The engine used to model "one subject, N batches"; the real college runs a
*lab window* where batches 1,2 do subject A while batches 3,4 do subject B at
the same time (COMP-TE-D: Lab CG D1D2 + Lab IIS D3D4). These tests prove the
window unit: two different lab subjects co-locate, siblings share a window
key, MAX_ONE_LAB_PER_DAY counts windows, and SAME_SUBJECT_SAME_DAY exempts
labs/tutorials.
"""
from app.tests.test_runner import (
    suite, test, seed_minimal, login_token, auth_headers, TestingSessionLocal,
)


def _add_param(db, profile_id, key, value, param_type="JSON"):
    from app.models.profiles import ProfileParameter, ParamType
    from sqlalchemy import select
    existing = db.scalars(
        select(ProfileParameter).where(
            ProfileParameter.profile_id == profile_id,
            ProfileParameter.param_key == key,
        )
    ).first()
    if existing:
        existing.param_value = value
        existing.param_type = ParamType(param_type)
    else:
        db.add(ProfileParameter(profile_id=profile_id, param_key=key,
                                param_value=value,
                                param_type=ParamType(param_type)))
    db.commit()


def _setup_window(ids, group_id, profile_id, db):
    """Two lab subjects each split into batches 1,2 and 3,4.

    Window 1: subj_a -> batches 1,2 (fac_a) + subj_b -> batches 3,4 (fac_b).
    Window 2: subj_b -> batches 1,2 (fac_b) + subj_a -> batches 3,4 (fac_a).
    This is the COMP-BE-A rotation, group-scoped (A1).
    """
    from app.models.subject_assignments import SubjectAssignment
    from app.models.profiles import ProfileResource, ResourceType
    from app.models.constraints import HardConstraint
    from app.models.faculty import Faculty
    from app.models.rooms import Room, RoomType
    from app.models.subjects import Subject

    fac_c = Faculty(name="Carol", email="carol@x.com", department="CS")
    fac_d = Faculty(name="Dave", email="dave@x.com", department="CS")
    db.add_all([fac_c, fac_d]); db.flush()
    room3 = Room(name="L3", room_code="L3", room_type=RoomType.LAB,
                 capacity=40, building="A")
    room4 = Room(name="L4", room_code="L4", room_type=RoomType.LAB,
                 capacity=40, building="A")
    room5 = Room(name="L5", room_code="L5", room_type=RoomType.LAB,
                 capacity=40, building="A")
    db.add_all([room3, room4, room5]); db.flush()
    subj_b = Subject(name="Data Structures", subject_code="CS-B1",
                     department="CS", semester=3, hours_per_week=2,
                     requires_lab=True)
    db.add(subj_b); db.flush()
    db.add_all([
        ProfileResource(profile_id=profile_id, resource_type=ResourceType.FACULTY,
                        resource_id=fac_c.id),
        ProfileResource(profile_id=profile_id, resource_type=ResourceType.FACULTY,
                        resource_id=fac_d.id),
        ProfileResource(profile_id=profile_id, resource_type=ResourceType.ROOM,
                        resource_id=room3.id),
        ProfileResource(profile_id=profile_id, resource_type=ResourceType.ROOM,
                        resource_id=room4.id),
        ProfileResource(profile_id=profile_id, resource_type=ResourceType.ROOM,
                        resource_id=room5.id),
        ProfileResource(profile_id=profile_id, resource_type=ResourceType.SUBJECT,
                        resource_id=subj_b.id),
    ])
    db.add(HardConstraint(
        profile_id=profile_id, constraint_type="CONTIGUOUS_LAB_SLOTS",
        config_json={"default_block_length": 1}))
    db.add(HardConstraint(
        profile_id=profile_id, constraint_type="MAX_ONE_LAB_PER_DAY",
        config_json={}))
    db.flush()
    # seed_minimal left a whole-division assignment for subj_a; the windows
    # replace it with per-batch rows.
    from sqlalchemy import delete as sa_delete
    db.execute(sa_delete(SubjectAssignment).where(
        SubjectAssignment.subject_id == ids["subject"],
        SubjectAssignment.group_id == group_id,
        SubjectAssignment.batch_number.is_(None)))
    # Window 1: subj_a b1,2 + subj_b b3,4  (each batch its own faculty, the
    # real "Lab CG D1D2 SuS/PD" pattern)
    fac_a2 = Faculty(name="Bob", email="bob@x.com", department="CS")
    db.add(fac_a2); db.flush()
    db.add(ProfileResource(profile_id=profile_id, resource_type=ResourceType.FACULTY,
                           resource_id=fac_a2.id))
    for b, f in ((1, ids["faculty"]), (2, fac_a2.id)):
        db.add(SubjectAssignment(subject_id=ids["subject"], faculty_id=f,
                                 group_id=group_id, weekly_hours=1, load_share=1.0,
                                 batch_number=b, period_number=1, block_length=1))
    for b, f in ((3, fac_c.id), (4, fac_d.id)):
        db.add(SubjectAssignment(subject_id=subj_b.id, faculty_id=f,
                                 group_id=group_id, weekly_hours=1, load_share=1.0,
                                 batch_number=b, period_number=1, block_length=1))
    # Window 2: subj_b b1,2 + subj_a b3,4  (the swap)
    for b, f in ((1, fac_c.id), (2, fac_d.id)):
        db.add(SubjectAssignment(subject_id=subj_b.id, faculty_id=f,
                                 group_id=group_id, weekly_hours=1, load_share=1.0,
                                 batch_number=b, period_number=2, block_length=1))
    for b, f in ((3, ids["faculty"]), (4, fac_a2.id)):
        db.add(SubjectAssignment(subject_id=ids["subject"], faculty_id=f,
                                 group_id=group_id, weekly_hours=1, load_share=1.0,
                                 batch_number=b, period_number=2, block_length=1))
    db.commit()
    return {"subj_b": subj_b.id, "fac_c": fac_c.id, "fac_d": fac_d.id, "fac_a2": fac_a2.id}


def _generate(client, headers, profile_id):
    r = client.post("/generate/", headers=headers, json={
        "profile_id": profile_id, "academic_year": "2025-26", "semester": 3,
        "timetable_type": "CLASS", "instances_requested": 1, "algorithm": "GREEDY",
    })
    assert r.status_code == 201, r.text
    gen = r.json()
    inst = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]
    return client.get(f"/instances/{inst['id']}/slots", headers=headers).json()


@suite("Phase 2 — Lab windows carry multiple subjects (A1)")
def _phase2_windows(s):
    @test("two lab subjects in one window are co-located and rotated")
    def t_window_co_located(client):
        from app.tests.test_runner import reset_db, create_admin, ensure_settings
        global ids
        reset_db(); create_admin()
        ensure_settings({"enable_soft_constraint_scoring": False})
        ids = seed_minimal(requires_lab=True, weekly_hours=1)
        db = TestingSessionLocal()
        try:
            _setup_window(ids, ids["group"], ids["profile"], db)
        finally:
            db.close()
        headers = auth_headers(login_token(client))
        slots = _generate(client, headers, ids["profile"])
        # 8 window members placed (2 windows x 4 batches), 1 slot each.
        lab_slots = [s for s in slots if s["batch_number"] is not None]
        assert len(lab_slots) == 8, f"expected 8 batch slots, got {len(lab_slots)}"
        # Group by window_key: each window's 4 batches at the same day+slot.
        from collections import defaultdict
        by_win = defaultdict(list)
        for s in lab_slots:
            assert s["window_key"], s
            by_win[s["window_key"]].append(s)
        assert len(by_win) == 2, f"expected 2 windows, got {len(by_win)}"
        for wk, members in by_win.items():
            days = {m["day_of_week"] for m in members}
            slots_n = {m["slot_number"] for m in members}
            assert len(days) == 1 and len(slots_n) == 1, (wk, members)
            batches = {m["batch_number"] for m in members}
            assert batches == {1, 2, 3, 4}, (wk, batches)
        # Rotation: window A has subj_a on batches 1,2; window B has it on 3,4.
        w1, w2 = by_win.values()
        w1 = sorted(w1, key=lambda m: m["batch_number"])
        w2 = sorted(w2, key=lambda m: m["batch_number"])
        a_batches_w1 = [m["batch_number"] for m in w1 if m["subject_id"] == ids["subject"]]
        a_batches_w2 = [m["batch_number"] for m in w2 if m["subject_id"] == ids["subject"]]
        assert a_batches_w1 == [1, 2], a_batches_w1
        assert a_batches_w2 == [3, 4], a_batches_w2

    @test("window siblings are not group double-book violations")
    def t_window_no_violation(client):
        from app.tests.test_runner import reset_db, create_admin, ensure_settings
        global ids
        reset_db(); create_admin()
        ensure_settings({"enable_soft_constraint_scoring": False})
        ids = seed_minimal(requires_lab=True, weekly_hours=1)
        db = TestingSessionLocal()
        try:
            _setup_window(ids, ids["group"], ids["profile"], db)
        finally:
            db.close()
        headers = auth_headers(login_token(client))
        r = client.post("/generate/", headers=headers, json={
            "profile_id": ids["profile"], "academic_year": "2025-26", "semester": 3,
            "timetable_type": "CLASS", "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        insts = client.get(f"/instances/{r.json()['id']}", headers=headers).json()
        for inst in insts:
            assert inst["hard_violations"] == 0, inst

    @test("MAX_ONE_LAB_PER_DAY counts windows, not subjects")
    def t_max_lab_counts_windows(client):
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY
        from app.engine.constraint_checker import SlotCandidate
        v = HARD_CONSTRAINT_REGISTRY["MAX_ONE_LAB_PER_DAY"]
        cand = SlotCandidate(instance_id=1, day_of_week=0, slot_number=2,
                             start_time=None, end_time=None, faculty_id=1,
                             room_id=1, student_group_id=1, subject_id=21,
                             session_type="LAB", batch_number=1,
                             window_key="w1:1")
        # A sibling of the SAME window is fine (different subject).
        sib = SlotCandidate(instance_id=1, day_of_week=0, slot_number=2,
                            start_time=None, end_time=None, faculty_id=2,
                            room_id=2, student_group_id=1, subject_id=22,
                            session_type="LAB", batch_number=2,
                            window_key="w1:1")
        class _Slot:
            def __init__(self, window_key, subject, batch):
                self.student_group_id = 1
                self.day_of_week = 0
                self.slot_number = 2
                self.session_type = "LAB"
                self.subject_id = subject
                self.batch_number = batch
                self.window_key = window_key
        # Same window, different subject: allowed.
        committed = [_Slot("w1:1", 22, 2)]
        assert v(sib, committed, {}, None) is None
        # Different window that day: rejected.
        other = SlotCandidate(instance_id=1, day_of_week=0, slot_number=3,
                              start_time=None, end_time=None, faculty_id=3,
                              room_id=3, student_group_id=1, subject_id=23,
                              session_type="LAB", batch_number=1,
                              window_key="w1:2")
        committed2 = [_Slot("w1:1", 21, 1)]
        assert v(other, committed2, {}, None) is not None

    @test("SAME_SUBJECT_SAME_DAY exempts labs and tutorials by default")
    def t_same_subject_lab_exempt(client):
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY
        from app.engine.constraint_checker import SlotCandidate
        v = HARD_CONSTRAINT_REGISTRY["SAME_SUBJECT_SAME_DAY"]
        # A lecture + lab of the same subject on one day is the 160 real
        # violations; default is lectures-only, so it must be allowed.
        cand_lab = SlotCandidate(instance_id=1, day_of_week=0, slot_number=2,
                                 start_time=None, end_time=None, faculty_id=1,
                                 room_id=1, student_group_id=1, subject_id=7,
                                 session_type="LAB")
        class _Slot:
            def __init__(self, stype):
                self.student_group_id = 1
                self.day_of_week = 0
                self.slot_number = 1
                self.subject_id = 7
                self.session_type = stype
                self.batch_number = None
        assert v(cand_lab, [_Slot("LECTURE")], {}, None) is None
        # Two lectures of the same subject same day: still rejected.
        cand_lec = SlotCandidate(instance_id=1, day_of_week=0, slot_number=2,
                                 start_time=None, end_time=None, faculty_id=1,
                                 room_id=1, student_group_id=1, subject_id=7,
                                 session_type="LECTURE")
        assert v(cand_lec, [_Slot("LECTURE")], {}, None) is not None

    @test("LAB_ROTATION_COMPLETE is an invariant rule and rejects a duplicate pairing")
    def t_rotation_registered(client):
        from app.engine.constraint_registry import (
            HARD_CONSTRAINT_REGISTRY, INVARIANT_RULES)
        from app.engine.constraint_checker import SlotCandidate
        assert "LAB_ROTATION_COMPLETE" in INVARIANT_RULES
        assert "LAB_ROTATION_COMPLETE" in HARD_CONSTRAINT_REGISTRY
        v = HARD_CONSTRAINT_REGISTRY["LAB_ROTATION_COMPLETE"]
        cand = SlotCandidate(instance_id=1, day_of_week=0, slot_number=2,
                             start_time=None, end_time=None, faculty_id=1,
                             room_id=1, student_group_id=1, subject_id=7,
                             session_type="LAB", batch_number=1,
                             window_key="w1:1")
        class _Slot:
            def __init__(self, batch, subject):
                self.student_group_id = 1
                self.batch_number = batch
                self.subject_id = subject
                self.session_type = "LAB"
        # Batch 1 already did subject 7 in an earlier window -> reject.
        committed = [_Slot(1, 7)]
        assert v(cand, committed, {}, None) is not None
        # Batch 2 doing subject 7 is a fresh pairing -> allowed.
        cand2 = SlotCandidate(instance_id=1, day_of_week=0, slot_number=2,
                              start_time=None, end_time=None, faculty_id=1,
                              room_id=1, student_group_id=1, subject_id=7,
                              session_type="LAB", batch_number=2,
                              window_key="w1:2")
        assert v(cand2, committed, {}, None) is None

    @test("OR-Tools co-locates window members and keeps labs (regression)")
    def t_ortools_windows(client):
        # Phase 2's window fix shipped a co-location formulation that forced
        # equality across EVERY room variant of every member — infeasible the
        # moment a member has two room candidates, so CP-SAT silently dropped
        # every lab. The fixed formulation uses one presence indicator per
        # (window, day, slot); this test pins it.
        from app.tests.test_runner import reset_db, create_admin, ensure_settings
        global ids
        reset_db(); create_admin()
        ensure_settings({"enable_soft_constraint_scoring": False})
        ids = seed_minimal(requires_lab=True, weekly_hours=1)
        db = TestingSessionLocal()
        try:
            _setup_window(ids, ids["group"], ids["profile"], db)
        finally:
            db.close()
        headers = auth_headers(login_token(client))
        r = client.post("/generate/", headers=headers, json={
            "profile_id": ids["profile"], "academic_year": "2025-26", "semester": 3,
            "timetable_type": "CLASS", "instances_requested": 1, "algorithm": "OR_TOOLS",
        })
        assert r.status_code == 201, r.text
        insts = client.get(f"/instances/{r.json()['id']}", headers=headers).json()
        assert insts, "expected instances"
        inst = insts[0]
        # The 2 windows x 4 batches must all be placed (no fabricated-lab loss).
        assert inst["hard_violations"] == 0, inst
        slots = client.get(
            f"/instances/{inst['id']}/slots", headers=headers).json()
        lab_slots = [s for s in slots if s["batch_number"] is not None]
        assert len(lab_slots) == 8, (
            f"expected 8 window member slots, got {len(lab_slots)}"
        )
        from collections import defaultdict
        by_win = defaultdict(list)
        for s in lab_slots:
            by_win[s["window_key"]].append(s)
        assert len(by_win) == 2, by_win
        for wk, members in by_win.items():
            assert len({m["day_of_week"] for m in members}) == 1, (wk, members)
            assert len({m["slot_number"] for m in members}) == 1, (wk, members)
            assert {m["batch_number"] for m in members} == {1, 2, 3, 4}, (
                wk, members)

    return [t_window_co_located, t_window_no_violation, t_max_lab_counts_windows,
            t_same_subject_lab_exempt, t_rotation_registered, t_ortools_windows]
