"""Phase 4 engine changes: A4 published-load bridge and A6 fail-fast.

- ``Scheduler._load_published_conflicts`` now also returns per-faculty
  day/week load counts from published instances, and the faculty daily/weekly
  caps measure the candidate against committed + published load (A4).
- ``ConstraintChecker.is_valid`` is fail-fast: it returns on the first
  violation instead of running every rule and collecting the full report
  (A6) — the solver only needs a boolean.
"""
from app.tests.test_runner import (
    suite, test, reset_db, create_admin, seed_minimal, TestingSessionLocal,
)


@suite("Phase 4 — A4 published-load bridge + A6 fail-fast")
def _phase4_engine(s):
    @test("is_valid stops at the first violation; check_all collects them")
    def t_fail_fast(client):
        from app.engine.constraint_checker import ConstraintChecker, SlotCandidate
        from app.models.generation import TimetableSlot, SessionType
        from datetime import time
        reset_db(); create_admin()
        ids = seed_minimal(weekly_hours=3)
        db = TestingSessionLocal()
        try:
            committed = [TimetableSlot(
                instance_id=1, day_of_week=0, slot_number=1,
                start_time=time(9), end_time=time(10),
                faculty_id=ids["faculty"], room_id=ids["classroom"],
                student_group_id=ids["group"], subject_id=ids["subject"],
                session_type=SessionType.LECTURE,
            )]
            checker = ConstraintChecker(db, committed, hard_constraints=[])
            # Same slot as the committed one: faculty AND room AND group clash.
            bad = SlotCandidate(1, 0, 1, time(9), time(10), ids["faculty"],
                                ids["classroom"], ids["group"], ids["subject"],
                                "LECTURE")
            full = checker.check_all(bad)
            assert len(full) >= 2, full
            assert not checker.is_valid(bad)
            fast = checker._check(bad, fail_fast=True)
            assert len(fast) == 1, fast
            # A free slot passes both paths.
            good = SlotCandidate(1, 0, 3, time(11), time(12), ids["faculty"],
                                 ids["classroom"], ids["group"], ids["subject"],
                                 "LECTURE")
            assert checker.is_valid(good)
            assert checker.check_all(good) == []
        finally:
            db.close()

    @test("published load counts toward the daily faculty cap")
    def t_published_day_cap(client):
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY
        from app.engine.constraint_checker import SlotCandidate, ConstraintContext
        from app.models.generation import TimetableSlot, SessionType
        from datetime import time
        reset_db(); create_admin()
        ids = seed_minimal(faculty_max_per_day=3)
        db = TestingSessionLocal()
        try:
            v = HARD_CONSTRAINT_REGISTRY["FACULTY_MAX_HOURS_PER_DAY"]
            committed = [TimetableSlot(
                instance_id=1, day_of_week=0, slot_number=1,
                start_time=time(9), end_time=time(10),
                faculty_id=ids["faculty"], room_id=ids["classroom"],
                student_group_id=ids["group"], subject_id=ids["subject"],
                session_type=SessionType.LECTURE,
            )]
            cand = SlotCandidate(1, 0, 2, time(10), time(11), ids["faculty"],
                                 ids["classroom"], ids["group"], ids["subject"],
                                 "LECTURE")
            # 1 committed + 1 candidate + 2 published = 4 > 3 -> violation.
            ctx = ConstraintContext(db, committed, reserved={
                "faculty_day_counts": {ids["faculty"]: {0: 2}},
                "faculty_week_counts": {ids["faculty"]: 4},
            })
            assert v(cand, committed, {}, ctx) is not None
            # Without published load the same candidate passes (2 <= 3).
            ctx2 = ConstraintContext(db, committed, reserved={})
            assert v(cand, committed, {}, ctx2) is None
        finally:
            db.close()

    @test("published load counts toward the weekly faculty cap")
    def t_published_week_cap(client):
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY
        from app.engine.constraint_checker import SlotCandidate, ConstraintContext
        from app.models.generation import TimetableSlot, SessionType
        from datetime import time
        reset_db(); create_admin()
        ids = seed_minimal(faculty_max_per_week=3)
        db = TestingSessionLocal()
        try:
            v = HARD_CONSTRAINT_REGISTRY["FACULTY_MAX_HOURS_PER_WEEK"]
            committed = [TimetableSlot(
                instance_id=1, day_of_week=0, slot_number=1,
                start_time=time(9), end_time=time(10),
                faculty_id=ids["faculty"], room_id=ids["classroom"],
                student_group_id=ids["group"], subject_id=ids["subject"],
                session_type=SessionType.LECTURE,
            )]
            cand = SlotCandidate(1, 0, 2, time(10), time(11), ids["faculty"],
                                 ids["classroom"], ids["group"], ids["subject"],
                                 "LECTURE")
            ctx = ConstraintContext(db, committed, reserved={
                "faculty_week_counts": {ids["faculty"]: 4},
            })
            assert v(cand, committed, {}, ctx) is not None
            ctx2 = ConstraintContext(db, committed, reserved={})
            assert v(cand, committed, {}, ctx2) is None
        finally:
            db.close()

    @test("_load_published_conflicts returns per-faculty day/week counts")
    def t_published_counts(client):
        from app.models.generation import (
            TimetableGeneration, TimetableInstance, TimetableSlot,
            GenerationStatus, InstanceStatus, SessionType, AlgorithmType,
            VariationMode,
        )
        from app.engine.scheduler import Scheduler
        from datetime import time
        reset_db(); create_admin()
        ids = seed_minimal()
        db = TestingSessionLocal()
        try:
            gen = TimetableGeneration(
                profile_id=ids["profile"], academic_year="2025-26", semester=3,
                timetable_type="CLASS", instances_requested=1,
                algorithm_used=AlgorithmType.GREEDY,
                variation=VariationMode.RANDOM, triggered_by=ids["admin"],
                generation_status=GenerationStatus.COMPLETED,
            )
            db.add(gen); db.flush()
            inst = TimetableInstance(generation_id=gen.id, instance_number=1,
                                     status=InstanceStatus.PUBLISHED)
            db.add(inst); db.flush()
            db.add_all([
                TimetableSlot(instance_id=inst.id, day_of_week=0, slot_number=1,
                              start_time=time(9), end_time=time(10),
                              faculty_id=ids["faculty"], room_id=ids["classroom"],
                              student_group_id=ids["group"], subject_id=ids["subject"],
                              session_type=SessionType.LECTURE),
                TimetableSlot(instance_id=inst.id, day_of_week=0, slot_number=2,
                              start_time=time(10), end_time=time(11),
                              faculty_id=ids["faculty"], room_id=ids["classroom"],
                              student_group_id=ids["group"], subject_id=ids["subject"],
                              session_type=SessionType.LECTURE),
                TimetableSlot(instance_id=inst.id, day_of_week=1, slot_number=1,
                              start_time=time(9), end_time=time(10),
                              faculty_id=ids["faculty"], room_id=ids["classroom"],
                              student_group_id=ids["group"], subject_id=ids["subject"],
                              session_type=SessionType.LECTURE),
            ])
            db.commit()
            reserved = Scheduler(db)._load_published_conflicts()
            assert reserved["faculty_day_counts"][ids["faculty"]] == {0: 2, 1: 1}
            assert reserved["faculty_week_counts"][ids["faculty"]] == 3
            assert (ids["faculty"], 0, 1) in reserved["faculty"]
            assert (ids["classroom"], 0, 2) in reserved["room"]
        finally:
            db.close()

    return [t_fail_fast, t_published_day_cap, t_published_week_cap,
            t_published_counts]
