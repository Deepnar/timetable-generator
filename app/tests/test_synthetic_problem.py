"""Synthetic problems (D4): the solver must place every planted session.

The generator plants a valid timetable by pattern and derives the solver's
inputs from it, so the problem is guaranteed-satisfiable: ANY unplaced
session is provably a solver bug. These are the CI golden tests — a solver
regression shows up here before it can hide in real-data ambiguity. The
"other fixture college" shape (D3: 6 slots, break at 3, 5-day, 2 batches,
2-slot labs, no home room) runs in the same harness: if it needs an
app/engine change, the engine has overfitted to TCET.
"""
from app.tests.test_runner import (
    suite, test, reset_db, create_admin, ensure_settings,
)


def _plant_and_solve(client, **shape):
    from app.tests.conftest import TestingSessionLocal
    from scripts.synthetic_problem import plant_problem
    from app.engine.profile_resolver import ProfileResolver
    from app.engine.solvers.greedy_solver import GreedySolver

    reset_db(); create_admin()
    ensure_settings({"enable_soft_constraint_scoring": False,
                     "enable_lab_batches": False})
    db = TestingSessionLocal()
    try:
        info = plant_problem(db, **shape)
        db.commit()
        resolved = ProfileResolver(db).resolve(info["profile"])
        solver = GreedySolver(db=db, profile=resolved, instance_id=9999)
        slots = solver.solve()
        return info, solver, slots
    finally:
        db.close()


def _assert_every_planted_placed(info, solver, slots):
    """Every planted session appears in the solve (any valid slot).

    Greedy is not required to reproduce the planted pattern exactly — the D4
    promise is placement-completeness: on a guaranteed-satisfiable problem an
    unplaced session is provably a solver bug. Validity is checked separately
    (the solver only commits candidates that pass every hard rule).
    """
    assert solver.unplaced_count == 0, f"{solver.unplaced_count} unplaced"
    placed = {(s.student_group_id, s.subject_id, s.faculty_id, s.batch_number)
              for s in slots}
    missing = [(gid, sid, fid, batch)
               for (gid, sid, fid, _d, _sn, _bl, batch) in info["planted"]
               if (gid, sid, fid, batch) not in placed]
    assert not missing, f"planted sessions missing from the solve: {missing}"


@suite("Phase 5 — Synthetic problems (D4): solver reproduces the plant")
def _phase5_synthetic(s):
    @test("default shape: every planted session is placed")
    def t_default(client):
        info, solver, slots = _plant_and_solve(client, divisions=2)
        _assert_every_planted_placed(info, solver, slots)

    @test("the other-fixture shape: no home rooms, 2-slot labs, break 3")
    def t_other_fixture(client):
        # D3's deliberately different college: 6 slots, break at 3, 5-day,
        # 2 batches, 2-slot labs, NO home room.
        info, solver, slots = _plant_and_solve(
            client, divisions=2, subjects_per_division=4, lecture_hours=3,
            batches=2, slots=6, break_slot=3, days=5, lab_block=2,
            home_rooms=False)
        _assert_every_planted_placed(info, solver, slots)
        # The home-room restriction must NOT apply: lectures may use any room.
        from app.models.generation import TimetableSlot
        from app.models.groups import StudentGroup
        from app.tests.conftest import TestingSessionLocal
        db = TestingSessionLocal()
        try:
            g = db.get(StudentGroup, info["groups"][0])
            assert g.home_room_id is None and g.home_room_secondary_id is None
            non_lab = [s for s in slots
                       if str(getattr(s.session_type, "value",
                                      s.session_type)).upper() != "LAB"]
            rooms = {s.room_id for s in non_lab}
            assert len(rooms) >= 2, f"expected scattered rooms, got {rooms}"
        finally:
            db.close()

    @test("big shape: 4 divisions, 4 subjects, 4 batches, 9 slots")
    def t_big(client):
        info, solver, slots = _plant_and_solve(
            client, divisions=4, subjects_per_division=4, lecture_hours=3,
            batches=4, slots=9, break_slot=4, days=5, lab_block=1,
            home_rooms=True)
        _assert_every_planted_placed(info, solver, slots)

    @test("a lab-heavy shape stresses window co-location")
    def t_lab_heavy(client):
        info, solver, slots = _plant_and_solve(
            client, divisions=2, subjects_per_division=5, lecture_hours=2,
            batches=3, slots=8, break_slot=4, days=5, lab_block=2,
            home_rooms=True)
        _assert_every_planted_placed(info, solver, slots)

    return [t_default, t_other_fixture, t_big, t_lab_heavy]
