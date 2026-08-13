"""Parallel practicals (DD-024): a class splits into lab batches that all run
at the same time in different rooms (3 for FE, 2 lab groups for SE+).

Tests the greedy expansion (`_expand_lab_batches`), the atomic parallel
placement (`_place_parallel_group`), the auto-derived batch count, the
`lab_batches` profile override, the max-one-lab-per-day registry rule, and the
graceful degradation when rooms/faculty are scarce.
"""
from datetime import time

from app.tests.test_runner import suite, test, seed_minimal, login_token, auth_headers
from app.engine.constraint_checker import SlotCandidate


def _add_faculty_and_room(client, db, profile_id, *, faculty_name, room_name,
                          room_type="LAB", capacity=40):
    """Attach one more faculty + one more room to the seed_minimal profile."""
    from app.models.faculty import Faculty
    from app.models.rooms import Room, RoomType
    from app.models.profiles import ProfileResource, ResourceType

    fac = Faculty(name=faculty_name, email=f"{faculty_name.lower().replace(' ', '.')}@x.com",
                  department="CS")
    db.add(fac)
    db.flush()
    room = Room(name=room_name, room_code=room_name,
                room_type=getattr(RoomType, room_type, RoomType.LAB),
                capacity=capacity, building="A")
    db.add(room)
    db.flush()
    db.add(ProfileResource(profile_id=profile_id, resource_type=ResourceType.FACULTY,
                           resource_id=fac.id))
    db.add(ProfileResource(profile_id=profile_id, resource_type=ResourceType.ROOM,
                           resource_id=room.id))
    db.commit()
    return fac.id, room.id


def _add_lab_block_rule(client, headers, profile_id):
    r = client.post("/constraints/hard", headers=headers, json={
        "profile_id": profile_id,
        "constraint_type": "CONTIGUOUS_LAB_SLOTS",
        "config_json": {"default_block_length": 2},
    })
    assert r.status_code == 201, r.text


def _gen_slots(client, headers, profile_id, algorithm="GREEDY"):
    r = client.post("/generate/", headers=headers, json={
        "profile_id": profile_id, "academic_year": "2025-26", "semester": 3,
        "timetable_type": "CLASS", "instances_requested": 1, "algorithm": algorithm,
    })
    assert r.status_code == 201, r.text
    gen = r.json()
    inst_id = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]["id"]
    return client.get(f"/instances/{inst_id}/slots", headers=headers).json()


@suite("Phase 5 — Parallel practicals (DD-024)")
def _phase5_parallel_labs(s):
    def _setup(year=2, weekly_hours=2):
        from app.tests.conftest import TestingSessionLocal
        ids = seed_minimal(requires_lab=True, weekly_hours=weekly_hours)
        db = TestingSessionLocal()
        try:
            from app.models.groups import StudentGroup
            from app.models.constraints import HardConstraint
            grp = db.get(StudentGroup, ids["group"])
            grp.year = year
            db.add(HardConstraint(
                profile_id=ids["profile"],
                constraint_type="CONTIGUOUS_LAB_SLOTS",
                config_json={"default_block_length": 2},
            ))
            db.commit()
            f2, r2 = _add_faculty_and_room(None, db, ids["profile"],
                                           faculty_name="Bob", room_name="L2")
            f3, r3 = _add_faculty_and_room(None, db, ids["profile"],
                                           faculty_name="Carol", room_name="L3")
            ids["faculty2"], ids["room2"] = f2, r2
            ids["faculty3"], ids["room3"] = f3, r3
            return ids, db
        except Exception:
            db.close()
            raise

    @test("a 2h lab block expands into per-batch parallel sessions")
    def t_expand(client):
        from app.engine.profile_resolver import ProfileResolver
        from app.engine.solvers.greedy_solver import GreedySolver
        from app.models.generation import SessionType
        from app.tests.conftest import TestingSessionLocal
        ids, db = _setup()
        try:
            resolved = ProfileResolver(db).resolve(ids["profile"])
            sol = GreedySolver(db, resolved, instance_id=1)
            sessions = sol._build_sessions()
            expanded = sol._expand_lab_batches(sessions)
            labs = [s for s in expanded if s.session_type == SessionType.LAB
                    and s.block_length >= 2]
            # SE+ (year 2) → 2 batches, distinct faculty, one parallel key.
            assert len(labs) == 2, f"expected 2 parallel lab sessions, got {len(labs)}"
            assert sorted(s.batch_number for s in labs) == [1, 2]
            assert len({s.faculty_id for s in labs}) == 2
            assert len({s.parallel_key for s in labs}) == 1
        finally:
            db.close()

    @test("greedy places both batches at the same time in distinct rooms")
    def t_parallel_placement(client):
        ids, db = _setup()
        db.close()
        headers = auth_headers(login_token(client))
        slots = _gen_slots(client, headers, ids["profile"])
        assert len(slots) == 4, f"2 batches x 2h = 4 slots, got {len(slots)}"
        by_batch = {}
        for sl in slots:
            by_batch.setdefault(sl["batch_number"], []).append(sl)
        assert set(by_batch) == {1, 2}, by_batch
        b1, b2 = by_batch[1], by_batch[2]
        for bs in (b1, b2):
            assert len(bs) == 2
            assert len({x["day_of_week"] for x in bs}) == 1
            assert len({x["room_id"] for x in bs}) == 1
            nums = sorted(x["slot_number"] for x in bs)
            assert nums == list(range(nums[0], nums[0] + 2)), f"not contiguous: {nums}"
        # Same time window, distinct rooms + distinct faculty.
        assert b1[0]["day_of_week"] == b2[0]["day_of_week"]
        assert b1[0]["slot_number"] == b2[0]["slot_number"]
        assert b1[0]["room_id"] != b2[0]["room_id"]
        assert b1[0]["faculty_id"] != b2[0]["faculty_id"]
        assert b1[0]["subject_id"] == b2[0]["subject_id"]

    @test("FE (year 1) derives three parallel batches")
    def t_fe_three_batches(client):
        ids, db = _setup(year=1)
        db.close()
        headers = auth_headers(login_token(client))
        slots = _gen_slots(client, headers, ids["profile"])
        assert len(slots) == 6, f"3 batches x 2h = 6 slots, got {len(slots)}"
        by_batch = {}
        for sl in slots:
            by_batch.setdefault(sl["batch_number"], []).append(sl)
        assert set(by_batch) == {1, 2, 3}, by_batch
        rooms = {sl["room_id"] for sl in slots}
        facs = {sl["faculty_id"] for sl in slots}
        assert len(rooms) == 3 and len(facs) == 3

    @test("lab_batches=1 disables parallelisation (whole-division lab)")
    def t_param_disable(client):
        from app.tests.conftest import TestingSessionLocal
        from app.models.profiles import ProfileParameter, ParamType
        ids, db = _setup()
        try:
            db.add(ProfileParameter(profile_id=ids["profile"], param_key="lab_batches",
                                    param_value="1", param_type=ParamType.INT))
            db.commit()
        finally:
            db.close()
        headers = auth_headers(login_token(client))
        slots = _gen_slots(client, headers, ids["profile"])
        assert len(slots) == 2, f"one whole-division 2h block, got {len(slots)}"
        assert all(sl["batch_number"] is None for sl in slots)
        assert len({sl["room_id"] for sl in slots}) == 1

    @test("scarce faculty degrades to a whole-division block")
    def t_scarce(client):
        ids = seed_minimal(requires_lab=True, weekly_hours=2)
        headers = auth_headers(login_token(client))
        _add_lab_block_rule(client, headers, ids["profile"])
        slots = _gen_slots(client, headers, ids["profile"])
        # Only one faculty in the profile pool → no parallel expansion possible.
        assert len(slots) == 2
        assert all(sl["batch_number"] is None for sl in slots)

    @test("MAX_ONE_LAB_PER_DAY rejects a second lab for the same group/day")
    def t_max_lab_day(client):
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY
        v = HARD_CONSTRAINT_REGISTRY["MAX_ONE_LAB_PER_DAY"]

        class _Slot:
            def __init__(self, gid, day, subject, stype, slot_number=1):
                self.student_group_id = gid
                self.day_of_week = day
                self.subject_id = subject
                self.session_type = stype
                self.slot_number = slot_number
                self.batch_number = None

        cand = SlotCandidate(
            instance_id=1, day_of_week=0, slot_number=2, start_time=time(10),
            end_time=time(11), faculty_id=1, room_id=1, student_group_id=1,
            subject_id=21, session_type="LAB",
        )
        # Same group already has a different lab subject that day → rejected.
        committed = [_Slot(1, 0, 11, "LAB")]
        assert v(cand, committed, {}, None) is not None
        # A lecture later that day is fine.
        assert v(SlotCandidate(instance_id=1, day_of_week=0, slot_number=3,
                               start_time=time(11), end_time=time(12),
                               faculty_id=1, room_id=1, student_group_id=1,
                               subject_id=22, session_type="LECTURE"),
                 committed, {}, None) is None
        # Parallel sibling of the same lab period is skipped.
        sib = SlotCandidate(instance_id=1, day_of_week=0, slot_number=2,
                            start_time=time(10), end_time=time(11),
                            faculty_id=2, room_id=2, student_group_id=1,
                            subject_id=21, session_type="LAB", batch_number=2)
        committed_sib = [_Slot(1, 0, 21, "LAB", slot_number=2)]
        committed_sib[0].batch_number = 1
        assert v(sib, committed_sib, {}, None) is None

    @test("parallel slots do not count as group double-book violations")
    def t_no_violation(client):
        ids, db = _setup()
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

    return [t_expand, t_parallel_placement, t_fe_three_batches,
            t_param_disable, t_scarce, t_max_lab_day, t_no_violation]
