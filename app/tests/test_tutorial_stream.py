"""Tutorial stream (DD-046): a subject runs as lectures AND tutorials.

The grid folds a subject's TUTORIAL cells into the assignment's weekly
hours; without the split every hour expanded as a LECTURE session and
SAME_SUBJECT_SAME_DAY (at most one lecture per day) needed one distinct day
per hour — 7 hours on a 5-day week left 2 sessions unplaced per subject on
IT-SE-C, while the college's own grid puts a lecture and a tutorial of the
same subject on the same day. `tutorial_hours` carries the split; the
tutorial stream is TUTORIAL-typed and exempt from the rule.
"""
from app.tests.test_runner import (
    suite, test, seed_minimal, login_token, auth_headers, TestingSessionLocal,
)


def _set_tutorial_hours(client, ids, weekly, tutorial):
    from app.models.subject_assignments import SubjectAssignment
    from sqlalchemy import select
    db = TestingSessionLocal()
    try:
        a = db.scalars(select(SubjectAssignment).where(
            SubjectAssignment.group_id == ids["group"],
            SubjectAssignment.subject_id == ids["subject"])).first()
        a.weekly_hours = weekly
        a.tutorial_hours = tutorial
        db.commit()
    finally:
        db.close()


def _generate(client, headers, profile_id):
    r = client.post("/generate/", headers=headers, json={
        "profile_id": profile_id, "academic_year": "2025-26", "semester": 3,
        "timetable_type": "CLASS", "instances_requested": 1, "algorithm": "GREEDY",
    })
    assert r.status_code == 201, r.text
    gen = r.json()
    inst = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]
    return client.get(f"/instances/{inst['id']}/slots", headers=headers).json()


@suite("Phase 5 — Tutorial stream (DD-046)")
def _phase5_tutorial_stream(s):
    @test("tutorial_hours expand as TUTORIAL sessions, all placed")
    def t_split_expands(client):
        from app.tests.test_runner import reset_db, create_admin, ensure_settings
        reset_db(); create_admin()
        ensure_settings({"enable_soft_constraint_scoring": False})
        # The IT-SE-C shape: 7 weekly hours, 3 of them tutorials, on a 5-day
        # week. Flattened, SAME_SUBJECT_SAME_DAY needs 7 distinct days and
        # leaves 2 unplaced; split, 4 lectures fit 4 days and the 3 tutorials
        # are exempt.
        ids = seed_minimal(weekly_hours=7)
        _set_tutorial_hours(client, ids, 7, 3)
        headers = auth_headers(login_token(client))
        slots = _generate(client, headers, ids["profile"])
        assert len(slots) == 7, f"expected 7 sessions, got {len(slots)}"
        types = [s["session_type"] for s in slots]
        assert types.count("TUTORIAL") == 3, types
        assert types.count("LECTURE") == 4, types

    @test("tutorial sessions are exempt from SAME_SUBJECT_SAME_DAY")
    def t_tutorial_shares_day(client):
        from app.tests.test_runner import reset_db, create_admin, ensure_settings
        reset_db(); create_admin()
        ensure_settings({"enable_soft_constraint_scoring": False})
        ids = seed_minimal(weekly_hours=2)
        _set_tutorial_hours(client, ids, 3, 1)
        headers = auth_headers(login_token(client))
        slots = _generate(client, headers, ids["profile"])
        assert len(slots) == 3, slots
        types = [s["session_type"] for s in slots]
        assert types.count("TUTORIAL") == 1, types
        assert types.count("LECTURE") == 2, types
        # The two lectures need two distinct days (the rule); the tutorial is
        # unconstrained — the college's grids put a lecture and a tutorial of
        # one subject on the same day (permissibility is pinned by the
        # validator test; greedy's spread scan is not required to pack them).
        lec_days = {s["day_of_week"] for s in slots
                    if s["session_type"] == "LECTURE"}
        assert len(lec_days) == 2, lec_days

    @test("tutorial sessions do not violate SAME_SUBJECT_SAME_DAY directly")
    def t_validator_exempts(client):
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY
        from app.engine.constraint_checker import SlotCandidate
        v = HARD_CONSTRAINT_REGISTRY["SAME_SUBJECT_SAME_DAY"]
        cand = SlotCandidate(instance_id=1, day_of_week=0, slot_number=2,
                             start_time=None, end_time=None, faculty_id=1,
                             room_id=1, student_group_id=1, subject_id=7,
                             session_type="TUTORIAL")
        class _Slot:
            def __init__(self):
                self.student_group_id = 1
                self.day_of_week = 0
                self.slot_number = 1
                self.subject_id = 7
                self.session_type = "LECTURE"
        assert v(cand, [_Slot()], {}, None) is None

    return [t_split_expands, t_tutorial_shares_day, t_validator_exempts]
