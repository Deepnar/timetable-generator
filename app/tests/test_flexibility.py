"""Phase 6 tests: the flexibility levers.

Four groups, mirroring the roadmap items:

1. Generic room requirements — ``Subject.requirements_json`` (room_types /
   min_capacity / features / session_type) matched against room attributes
   (``Room.equipment_json`` + legacy booleans) instead of the binary
   ``requires_lab`` flag.
2. The ``enable_lab_batches`` college flag gates the LAB_BATCH_ROTATION rule.
3. CUSTOM escape hatches on the roomtype and sessiontype enums.
4. API/CSV round-trips for the new JSON columns.
"""
from datetime import time

from app.tests.test_runner import suite, test, seed_minimal


def _room_type(value):
    class _T:
        def __init__(self, v):
            self.value = v
    return _T(value)


def _simple_room(room_type="CLASSROOM", capacity=60, equipment=None,
                 has_projector=False, has_ac=False):
    class _R:
        def __init__(self):
            self.room_type = _room_type(room_type)
            self.capacity = capacity
            self.equipment_json = equipment or []
            self.has_projector = has_projector
            self.has_ac = has_ac
    return _R()


def _simple_subject(requirements=None, requires_lab=False):
    class _S:
        def __init__(self):
            self.requirements_json = requirements
            self.requires_lab = requires_lab
    return _S()


@suite("Phase 6 — Generic room requirements")
def _phase6_requirements(s):
    @test("effective_requirements: requirements_json wins, then requires_lab, then none")
    def t_effective(client):
        from app.engine.resource_requirements import effective_requirements
        assert effective_requirements(_simple_subject(
            requirements={"room_types": ["LAB"]}, requires_lab=False)) == {
            "room_types": ["LAB"]}
        # An explicit empty dict means "no constraints" even with requires_lab.
        assert effective_requirements(_simple_subject(
            requirements={}, requires_lab=True)) == {}
        # requires_lab is the legacy shorthand for a LAB room.
        assert effective_requirements(_simple_subject(requires_lab=True)) == {
            "room_types": ["LAB"]}
        assert effective_requirements(_simple_subject()) == {}

    @test("subject_session_type: declared session_type overrides the derived kind")
    def t_session_type(client):
        from app.models.generation import SessionType
        from app.engine.resource_requirements import subject_session_type
        assert subject_session_type(_simple_subject(
            requires_lab=True)) == SessionType.LAB
        assert subject_session_type(_simple_subject()) == SessionType.LECTURE
        assert subject_session_type(_simple_subject(
            requirements={"session_type": "SEMINAR"})) == SessionType.SEMINAR
        assert subject_session_type(_simple_subject(
            requirements={"session_type": "CUSTOM"})) == SessionType.CUSTOM
        # A bogus declared type falls back to the derived kind.
        assert subject_session_type(_simple_subject(
            requirements={"session_type": "NOT_A_THING"},
            requires_lab=True)) == SessionType.LAB

    @test("room_matches_requirements checks type, capacity and features")
    def t_room_match(client):
        from app.engine.resource_requirements import room_matches_requirements
        lab = _simple_room(room_type="LAB", capacity=40,
                           equipment=["projector"], has_ac=True)
        # room_types
        assert room_matches_requirements(
            lab, {"room_types": ["LAB"]})[0] is True
        assert room_matches_requirements(
            lab, {"room_types": ["SEMINAR_HALL"]})[0] is False
        assert room_matches_requirements(
            lab, {"room_types": ["LAB", "SEMINAR_HALL"]})[0] is True
        # min_capacity
        assert room_matches_requirements(
            lab, {"min_capacity": 40})[0] is True
        assert room_matches_requirements(
            lab, {"min_capacity": 41})[0] is False
        # features matched against equipment_json tags
        assert room_matches_requirements(
            lab, {"features": ["projector"]})[0] is True
        assert room_matches_requirements(
            lab, {"features": ["whiteboard"]})[0] is False
        # legacy boolean columns are sugar for the projector/ac tags
        assert room_matches_requirements(
            lab, {"features": ["ac"]})[0] is True
        plain = _simple_room(room_type="CLASSROOM")
        assert room_matches_requirements(
            plain, {"features": ["ac"]})[0] is False
        # absent requirements match any room
        assert room_matches_requirements(lab, {})[0] is True

    @test("the solver places a session on the room its requirements select")
    def t_solver_room(client):
        from app.models.subjects import Subject
        from app.tests.test_runner import login_token, auth_headers, TestingSessionLocal
        ids = seed_minimal(requires_lab=True)
        db = TestingSessionLocal()
        try:
            subj = db.get(Subject, ids["subject"])
            # Only a LAB room matches, even though requires_lab is also set.
            subj.requirements_json = {"room_types": ["LAB"]}
            db.commit()
        finally:
            db.close()

        headers = auth_headers(login_token(client))
        r = client.post("/generate/", headers=headers, json={
            "profile_id": ids["profile"], "academic_year": "2025-26",
            "semester": 3, "timetable_type": "CLASS",
            "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        inst_id = client.get(
            f"/instances/{gen['id']}", headers=headers).json()[0]["id"]
        slots = client.get(
            f"/instances/{inst_id}/slots", headers=headers).json()
        assert len(slots) == 3, slots
        assert {sl["room_id"] for sl in slots} == {ids["lab"]}, slots

    @test("a session_type declared in requirements_json lands on the slot")
    def t_solver_session_type(client):
        from app.models.subjects import Subject
        from app.tests.test_runner import login_token, auth_headers, TestingSessionLocal
        ids = seed_minimal()
        db = TestingSessionLocal()
        try:
            subj = db.get(Subject, ids["subject"])
            subj.requirements_json = {"session_type": "SEMINAR"}
            db.commit()
        finally:
            db.close()

        headers = auth_headers(login_token(client))
        r = client.post("/generate/", headers=headers, json={
            "profile_id": ids["profile"], "academic_year": "2025-26",
            "semester": 3, "timetable_type": "CLASS",
            "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        inst_id = client.get(
            f"/instances/{gen['id']}", headers=headers).json()[0]["id"]
        slots = client.get(
            f"/instances/{inst_id}/slots", headers=headers).json()
        assert len(slots) == 3, slots
        assert {sl["session_type"] for sl in slots} == {"SEMINAR"}, slots

    @test("a subject with no matching room schedules zero sessions")
    def t_no_matching_room(client):
        from app.models.subjects import Subject
        from app.tests.test_runner import login_token, auth_headers, TestingSessionLocal
        ids = seed_minimal()
        db = TestingSessionLocal()
        try:
            subj = db.get(Subject, ids["subject"])
            subj.requirements_json = {"room_types": ["AUDITORIUM"]}
            db.commit()
        finally:
            db.close()

        headers = auth_headers(login_token(client))
        r = client.post("/generate/", headers=headers, json={
            "profile_id": ids["profile"], "academic_year": "2025-26",
            "semester": 3, "timetable_type": "CLASS",
            "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        inst_id = client.get(
            f"/instances/{gen['id']}", headers=headers).json()[0]["id"]
        slots = client.get(
            f"/instances/{inst_id}/slots", headers=headers).json()
        assert slots == [], slots

    return [t_effective, t_session_type, t_room_match,
            t_solver_room, t_solver_session_type, t_no_matching_room]


@suite("Phase 6 — enable_lab_batches gates lab batch rotation")
def _phase6_lab_batches(s):
    @test("LAB_BATCH_ROTATION is inert while the college flag is off")
    def t_gate_off(client):
        from app.engine.constraint_registry import (
            HARD_CONSTRAINT_REGISTRY, ConstraintContext)
        from app.engine.constraint_checker import SlotCandidate
        from app.services.settings_service import get_settings
        from app.tests.test_runner import (
            reset_db, create_admin, ensure_settings, TestingSessionLocal)

        reset_db()
        ensure_settings({"enable_lab_batches": False})
        create_admin()
        db = TestingSessionLocal()
        try:
            settings = get_settings(db)
            ctx = ConstraintContext(db, [], settings=settings)
            v = HARD_CONSTRAINT_REGISTRY["LAB_BATCH_ROTATION"]
            cfg = {"group_days": {"11": [0]}}  # group 11 only on Monday
            cand = SlotCandidate(
                instance_id=1, day_of_week=1, slot_number=1,
                start_time=time(9), end_time=time(10), faculty_id=1,
                room_id=1, student_group_id=11, subject_id=1,
                session_type="LAB",
            )
            # Flag off (the default): the rule must not fire, even on a
            # disallowed weekday.
            assert v(cand, [], cfg, ctx) is None
        finally:
            db.close()

    @test("LAB_BATCH_ROTATION enforces weekdays once the flag is on")
    def t_gate_on(client):
        from app.engine.constraint_registry import (
            HARD_CONSTRAINT_REGISTRY, ConstraintContext)
        from app.engine.constraint_checker import SlotCandidate
        from app.services.settings_service import get_settings
        from app.tests.test_runner import (
            reset_db, create_admin, ensure_settings, TestingSessionLocal)

        reset_db()
        ensure_settings({"enable_lab_batches": True})
        create_admin()
        db = TestingSessionLocal()
        try:
            settings = get_settings(db)
            ctx = ConstraintContext(db, [], settings=settings)
            v = HARD_CONSTRAINT_REGISTRY["LAB_BATCH_ROTATION"]
            cfg = {"group_days": {"11": [0]}}

            def _cand(day):
                return SlotCandidate(
                    instance_id=1, day_of_week=day, slot_number=1,
                    start_time=time(9), end_time=time(10), faculty_id=1,
                    room_id=1, student_group_id=11, subject_id=1,
                    session_type="LAB",
                )
            assert v(_cand(1), [], cfg, ctx) is not None   # Tuesday blocked
            assert v(_cand(0), [], cfg, ctx) is None         # Monday allowed
        finally:
            db.close()

    return [t_gate_off, t_gate_on]


@suite("Phase 6 — CUSTOM escape hatches")
def _phase6_custom(s):
    @test("roomtype and sessiontype enums carry a CUSTOM label")
    def t_enum_values(client):
        from app.models.rooms import RoomType
        from app.models.generation import SessionType
        assert RoomType.CUSTOM.value == "CUSTOM"
        assert SessionType.CUSTOM.value == "CUSTOM"

    @test("POST /rooms accepts room_type CUSTOM and equipment_json")
    def t_api_rooms(client):
        from app.tests.test_runner import (
            reset_db, create_admin, login_token, auth_headers)
        reset_db(); create_admin()
        headers = auth_headers(login_token(client))
        r = client.post("/rooms/", headers=headers, json={
            "name": "Exam Hall", "room_code": "EH1",
            "room_type": "CUSTOM", "capacity": 200,
            "equipment_json": ["desk", "projector"],
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["room_type"] == "CUSTOM", body
        assert body["equipment_json"] == ["desk", "projector"], body

    @test("POST /subjects accepts requirements_json")
    def t_api_subjects(client):
        from app.tests.test_runner import (
            reset_db, create_admin, login_token, auth_headers)
        reset_db(); create_admin()
        headers = auth_headers(login_token(client))
        r = client.post("/subjects/", headers=headers, json={
            "name": "Design Studio", "subject_code": "DS101",
            "department": "ARCH", "semester": 4, "hours_per_week": 3,
            "requires_lab": False,
            "requirements_json": {"room_types": ["LAB"], "min_capacity": 30},
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["requirements_json"] == {
            "room_types": ["LAB"], "min_capacity": 30}, body

    @test("rooms CSV import parses the equipment_json column")
    def t_csv_rooms(client):
        from app.tests.test_runner import (
            reset_db, create_admin, login_token, auth_headers)
        reset_db(); create_admin()
        headers = auth_headers(login_token(client))
        csv_text = "\n".join([
            "name,room_code,room_type,capacity,building,floor,has_projector,has_ac,equipment_json",
            'Sem Hall,SH1,SEMINAR_HALL,60,A,1,false,false,"[""projector"",""whiteboard""]"',
        ])
        r = client.post(
            "/import/rooms", headers=headers,
            files={"file": ("rooms.csv", csv_text, "text/csv")},
        )
        assert r.status_code == 200, r.text
        assert r.json()["inserted"] == 1, r.text
        rooms = client.get("/rooms/", headers=headers).json()
        assert rooms[0]["equipment_json"] == ["projector", "whiteboard"], rooms

    @test("subjects CSV import parses the requirements_json column")
    def t_csv_subjects(client):
        from app.tests.test_runner import (
            reset_db, create_admin, login_token, auth_headers)
        reset_db(); create_admin()
        headers = auth_headers(login_token(client))
        csv_text = "\n".join([
            "name,subject_code,department,semester,hours_per_week,requires_lab,requirements_json",
            'Networks,NET201,CS,3,4,false,"{""room_types"":[""LAB""],""min_capacity"":30}"',
        ])
        r = client.post(
            "/import/subjects", headers=headers,
            files={"file": ("subjects.csv", csv_text, "text/csv")},
        )
        assert r.status_code == 200, r.text
        assert r.json()["inserted"] == 1, r.text
        subjects = client.get("/subjects/", headers=headers).json()
        assert subjects[0]["requirements_json"] == {
            "room_types": ["LAB"], "min_capacity": 30}, subjects

    return [t_enum_values, t_api_rooms, t_api_subjects,
            t_csv_rooms, t_csv_subjects]
