"""Phase 1 — Make the grid real (A2, A5).

Break is a numbered slot, slot times come verbatim from the grid, Saturday is
gated by a policy, and a division's lectures are hard-restricted to its home
room(s). These tests prove each behaviour in isolation with the toy seed.
"""
from app.tests.test_runner import (
    suite, test, seed_minimal, login_token, auth_headers, TestingSessionLocal,
)


def _add_param(db, profile_id, key, value, param_type="JSON"):
    """Insert or update a profile parameter (profile params are unique per key)."""
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


def _set_home_rooms(db, group_id, room_ids):
    from app.models.groups import StudentGroup
    grp = db.get(StudentGroup, group_id)
    grp.home_room_id = room_ids[0]
    grp.home_room_secondary_id = room_ids[1] if len(room_ids) > 1 else None
    db.commit()


def _generate(client, headers, profile_id):
    r = client.post("/generate/", headers=headers, json={
        "profile_id": profile_id, "academic_year": "2025-26",
        "semester": 3, "timetable_type": "CLASS",
        "instances_requested": 1, "algorithm": "GREEDY",
    })
    assert r.status_code == 201, r.text
    gen = r.json()
    inst = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]
    slots = client.get(f"/instances/{inst['id']}/slots", headers=headers).json()
    return slots


@suite("Phase 1 — break slots are non-teaching (A2)")
def _phase1_break_slots(s):
    @test("a session is never placed in a declared break slot")
    def t_break_skipped(client):
        from app.tests.test_runner import reset_db, create_admin, ensure_settings
        reset_db(); create_admin()
        ensure_settings({"enable_soft_constraint_scoring": False})
        db = TestingSessionLocal()
        try:
            ids = seed_minimal(weekly_hours=5)
            _add_param(db, ids["profile"], "break_slots", "[2]")
            _add_param(db, ids["profile"], "slot_times",
                       '[["08:30","09:30"],["09:30","10:30"],["10:30","11:30"],'
                       '["11:30","12:30"],["12:30","13:30"]]')
            db.commit()
        finally:
            db.close()
        headers = auth_headers(login_token(client))
        slots = _generate(client, headers, ids["profile"])
        assert slots, "expected some slots"
        for slot in slots:
            assert slot["slot_number"] != 2, slot
            assert slot["start_time"] == "10:30" or slot["slot_number"] not in (2,), slot

    @test("slot times come verbatim from the grid, not synthetic arithmetic")
    def t_verbatim_times(client):
        from app.tests.test_runner import reset_db, create_admin, ensure_settings
        reset_db(); create_admin()
        ensure_settings({"enable_soft_constraint_scoring": False})
        db = TestingSessionLocal()
        try:
            ids = seed_minimal(weekly_hours=3)
            # 4 slots, 45-minute grid (like an evening programme); nothing
            # injected. Verbatim times must win over day_start/slot_duration.
            _add_param(db, ids["profile"], "slot_times",
                       '[["08:00","08:45"],["08:45","09:30"],'
                       '["09:30","10:15"],["10:15","11:00"]]')
            _add_param(db, ids["profile"], "slots_per_day", "4", "INT")
            db.commit()
        finally:
            db.close()
        headers = auth_headers(login_token(client))
        slots = _generate(client, headers, ids["profile"])
        assert slots, "expected some slots"
        # SAME_SUBJECT_SAME_DAY spreads the 3 sessions across 3 days, each on
        # the first slot — the verbatim 45-minute times must appear, and no
        # synthetic 60-minute 09:00-start time may leak through.
        seen = {(sl["day_of_week"], sl["slot_number"],
                 sl["start_time"], sl["end_time"]) for sl in slots}
        assert seen, slots
        assert all(sl["start_time"].startswith("08:00") for sl in slots), slots
        assert all(sl["end_time"].startswith("08:45") for sl in slots), slots

    @test("NO_TEACHING_IN_BREAK_SLOT is a registered structural rule")
    def t_validator_registered(client):
        from app.engine.constraint_registry import (
            HARD_CONSTRAINT_REGISTRY, STRUCTURAL_RULES)
        assert "NO_TEACHING_IN_BREAK_SLOT" in STRUCTURAL_RULES
        assert "NO_TEACHING_IN_BREAK_SLOT" in HARD_CONSTRAINT_REGISTRY

    return [t_break_skipped, t_verbatim_times, t_validator_registered]


@suite("Phase 1 — saturday policy (A2)")
def _phase1_saturday(s):
    @test("saturday_policy=NONE keeps sessions off Saturday")
    def t_sat_none(client):
        from app.tests.test_runner import reset_db, create_admin, ensure_settings
        reset_db(); create_admin()
        ensure_settings({"enable_soft_constraint_scoring": False})
        db = TestingSessionLocal()
        try:
            ids = seed_minimal(weekly_hours=5)
            _add_param(db, ids["profile"], "working_days",
                       '["MON","TUE","WED","THU","FRI","SAT"]')
            _add_param(db, ids["profile"], "saturday_policy", "NONE", "STRING")
            db.commit()
        finally:
            db.close()
        headers = auth_headers(login_token(client))
        slots = _generate(client, headers, ids["profile"])
        assert slots, "expected some slots"
        assert all(sl["day_of_week"] != 5 for sl in slots), slots

    @test("saturday_policy=FULL allows Saturday")
    def t_sat_full(client):
        from app.tests.test_runner import reset_db, create_admin, ensure_settings
        reset_db(); create_admin()
        ensure_settings({"enable_soft_constraint_scoring": False})
        db = TestingSessionLocal()
        try:
            ids = seed_minimal(weekly_hours=6)
            _add_param(db, ids["profile"], "working_days",
                       '["MON","TUE","WED","THU","FRI","SAT"]')
            _add_param(db, ids["profile"], "saturday_policy", "FULL", "STRING")
            db.commit()
        finally:
            db.close()
        headers = auth_headers(login_token(client))
        slots = _generate(client, headers, ids["profile"])
        assert slots, "expected some slots"
        assert any(sl["day_of_week"] == 5 for sl in slots), slots

    return [t_sat_none, t_sat_full]


@suite("Phase 1 — home rooms restrict the room domain (A5)")
def _phase1_home_rooms(s):
    @test("a lecture never leaves the division's home rooms")
    def t_home_restriction(client):
        from app.tests.test_runner import reset_db, create_admin, ensure_settings
        reset_db(); create_admin()
        ensure_settings({"enable_soft_constraint_scoring": False})
        db = TestingSessionLocal()
        try:
            ids = seed_minimal(weekly_hours=3)
            # The group's home room is R1; R2 exists in the pool but is NOT the
            # venue, so every lecture must land in R1.
            _set_home_rooms(db, ids["group"], [ids["classroom"]])
            db.commit()
        finally:
            db.close()
        headers = auth_headers(login_token(client))
        slots = _generate(client, headers, ids["profile"])
        assert slots, "expected some slots"
        for sl in slots:
            assert sl["room_id"] == ids["classroom"], sl

    @test("ROOM_STABILITY soft scorer rewards venue fidelity")
    def t_scorer(client):
        from app.engine.scorer import (
            SOFT_CONSTRAINT_REGISTRY, ScoringContext, score_instance)
        assert "ROOM_STABILITY" in SOFT_CONSTRAINT_REGISTRY
        db = TestingSessionLocal()
        try:
            ids = seed_minimal(weekly_hours=3)
            _set_home_rooms(db, ids["group"], [ids["classroom"]])
            from app.models.generation import TimetableSlot, SessionType
            in_home = TimetableSlot(
                instance_id=1, day_of_week=0, slot_number=1,
                start_time=None, end_time=None, faculty_id=ids["faculty"],
                room_id=ids["classroom"], student_group_id=ids["group"],
                subject_id=ids["subject"], session_type=SessionType.LECTURE,
            )
            out = TimetableSlot(
                instance_id=1, day_of_week=0, slot_number=2,
                start_time=None, end_time=None, faculty_id=ids["faculty"],
                room_id=ids["lab"], student_group_id=ids["group"],
                subject_id=ids["subject"], session_type=SessionType.LECTURE,
            )
            ctx = ScoringContext(db)
            from app.models.constraints import SoftConstraint
            rule = SoftConstraint(constraint_type="ROOM_STABILITY",
                                  config_json={}, weight=1.0)
            sc = SOFT_CONSTRAINT_REGISTRY["ROOM_STABILITY"]
            assert sc([in_home, in_home], {}, ctx) == 1.0
            assert sc([in_home, out], {}, ctx) == 0.5
        finally:
            db.close()

    return [t_home_restriction, t_scorer]
