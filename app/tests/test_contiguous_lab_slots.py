"""Phase 2 tests: CONTIGUOUS_LAB_SLOTS registry rule (multi-slot lab blocks).

A lab subject governed by the rule has its ``weekly_hours`` expanded into
blocks of the configured size (a remainder stays single-slot), and each block
is placed as consecutive slots in the same room/teacher/group on one day. The
rule exercises the engine end to end: session expansion, block-aware
double-booking in the checker, and block variables in the OR-Tools model.
"""
from datetime import time

from app.tests.test_runner import suite, test, seed_minimal
from app.engine.constraint_checker import SlotCandidate


@suite("Phase 2 — CONTIGUOUS_LAB_SLOTS registry rule")
def _phase2_contiguous_lab_slots(s):
    def _gen_slots(client, headers, profile_id, algorithm="GREEDY"):
        r = client.post("/generate/", headers=headers, json={
            "profile_id": profile_id, "academic_year": "2025-26", "semester": 3,
            "timetable_type": "CLASS", "instances_requested": 1, "algorithm": algorithm,
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        inst_id = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]["id"]
        return client.get(f"/instances/{inst_id}/slots", headers=headers).json()

    def _add_rule(client, headers, profile_id, subject_id, config):
        r = client.post("/constraints/hard", headers=headers, json={
            "profile_id": profile_id,
            "constraint_type": "CONTIGUOUS_LAB_SLOTS",
            "config_json": config,
        })
        assert r.status_code == 201, r.text

    def _cand(subject_id=11, slot_number=1, block_length=3):
        return SlotCandidate(
            instance_id=1, day_of_week=0, slot_number=slot_number,
            start_time=time(9), end_time=time(12), faculty_id=1, room_id=1,
            student_group_id=1, subject_id=subject_id, session_type="LAB",
            block_length=block_length,
        )

    @test("configured_block_length resolves subject config and default")
    def t_config(client):
        from app.engine.constraint_registry import configured_block_length
        cfg = {"block_lengths": {"11": 3}, "default_block_length": 2}
        assert configured_block_length(11, cfg) == 3      # explicit wins
        assert configured_block_length(12, cfg) == 2      # falls back to default
        assert configured_block_length(12, {"block_lengths": {"11": 3}}) is None
        assert configured_block_length(11, None) is None
        assert configured_block_length(11, {}) is None

    @test("_contiguous_lab_slots validator checks the block size")
    def t_validator(client):
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY
        v = HARD_CONSTRAINT_REGISTRY["CONTIGUOUS_LAB_SLOTS"]
        cfg = {"block_lengths": {"11": 3}}
        assert v(_cand(block_length=3), [], cfg, None) is None          # correct size
        assert v(_cand(block_length=2), [], cfg, None) is not None       # wrong size
        assert v(_cand(block_length=1), [], cfg, None) is None           # single slot
        assert v(_cand(99, block_length=3), [], cfg, None) is None       # unlisted subject
        assert v(_cand(block_length=3), [], {}, None) is None            # empty config

    @test("SUBJECT_TIME_PREFERENCE bounds a block's last slot")
    def t_time_pref_block(client):
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY
        v = HARD_CONSTRAINT_REGISTRY["SUBJECT_TIME_PREFERENCE"]
        cfg = {"subject_id": 11, "max_slot": 3}
        assert v(_cand(slot_number=1, block_length=3), [], cfg, None) is None   # 1..3 ok
        assert v(_cand(slot_number=2, block_length=3), [], cfg, None) is not None  # ends at 4
        assert v(_cand(slot_number=3, block_length=1), [], cfg, None) is None
        assert v(_cand(slot_number=4, block_length=1), [], cfg, None) is not None

    @test("MAX_CONSECUTIVE_SAME_TEACHER counts a block as one run")
    def t_consecutive_block(client):
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY

        class _Slot:
            def __init__(self, fid, day, sn):
                self.faculty_id, self.day_of_week, self.slot_number = fid, day, sn

        v = HARD_CONSTRAINT_REGISTRY["MAX_CONSECUTIVE_SAME_TEACHER"]
        # committed slot 2 + a 3-slot block at 3..5 => one run of 4.
        committed = [_Slot(1, 0, 2)]
        assert v(_cand(slot_number=3, block_length=3), committed, {"max": 4}, None) is None
        assert v(_cand(slot_number=3, block_length=3), committed, {"max": 3}, None) is not None

    @test("greedy places a lab block as contiguous slots on one day")
    def t_greedy_block(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal(requires_lab=True, weekly_hours=3)
        headers = auth_headers(login_token(client))
        _add_rule(client, headers, ids["profile"], ids["subject"],
                  {"block_lengths": {str(ids["subject"]): 3}})
        slots = _gen_slots(client, headers, ids["profile"])
        assert len(slots) == 3, f"expected one 3-slot block, got {len(slots)} slots"
        assert len({sl["day_of_week"] for sl in slots}) == 1, slots
        assert len({sl["room_id"] for sl in slots}) == 1, slots
        nums = sorted(sl["slot_number"] for sl in slots)
        assert nums == list(range(nums[0], nums[0] + 3)), f"not contiguous: {nums}"
        # All three slots carry the same session identity (faculty/group/subject).
        assert len({sl["faculty_id"] for sl in slots}) == 1, slots
        assert len({sl["subject_id"] for sl in slots}) == 1, slots
        # start_time is the first slot's start; end_time the last slot's end.
        assert slots[0]["start_time"] < slots[-1]["end_time"], slots

    @test("greedy splits weekly hours into blocks plus a single-slot remainder")
    def t_greedy_remainder(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal(requires_lab=True, weekly_hours=4)
        headers = auth_headers(login_token(client))
        _add_rule(client, headers, ids["profile"], ids["subject"],
                  {"block_lengths": {str(ids["subject"]): 3}})
        slots = _gen_slots(client, headers, ids["profile"])
        assert len(slots) == 4, f"expected 3-block + 1 remainder, got {len(slots)}"
        by_day: dict[int, list[int]] = {}
        for sl in slots:
            by_day.setdefault(sl["day_of_week"], []).append(sl["slot_number"])
        # The block of 3 is contiguous on its day; the remainder lands on a
        # different day (SAME_SUBJECT_SAME_DAY forbids a second slot on the
        # block's day).
        trio = next(sorted(nums) for nums in by_day.values() if len(nums) == 3)
        assert trio == list(range(trio[0], trio[0] + 3)), f"block not contiguous: {trio}"
        assert len(by_day) == 2, f"expected 2 days, got {by_day}"

    @test("default_block_length forms blocks for every lab subject")
    def t_greedy_default(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal(requires_lab=True, weekly_hours=3)
        headers = auth_headers(login_token(client))
        _add_rule(client, headers, ids["profile"], ids["subject"],
                  {"default_block_length": 3})
        slots = _gen_slots(client, headers, ids["profile"])
        assert len(slots) == 3, slots
        nums = sorted(sl["slot_number"] for sl in slots)
        assert nums == list(range(nums[0], nums[0] + 3)), f"not contiguous: {nums}"

    @test("a lab subject without the rule keeps single-slot sessions")
    def t_no_rule(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal(requires_lab=True, weekly_hours=3)
        headers = auth_headers(login_token(client))
        slots = _gen_slots(client, headers, ids["profile"])
        assert len(slots) == 3, slots
        # SAME_SUBJECT_SAME_DAY spreads the three hours across days.
        assert len({sl["day_of_week"] for sl in slots}) == 3, slots

    @test("the checker rejects a block overlapping a committed slot")
    def t_checker_overlap(client):
        from app.engine.constraint_checker import ConstraintChecker
        from app.models.generation import TimetableSlot, SessionType
        from app.tests.conftest import TestingSessionLocal
        seed_minimal()
        db = TestingSessionLocal()
        try:
            committed = [TimetableSlot(
                instance_id=1, day_of_week=0, slot_number=4,
                start_time=time(10), end_time=time(11), faculty_id=1, room_id=1,
                student_group_id=1, subject_id=9, session_type=SessionType.LECTURE,
            )]
            checker = ConstraintChecker(db, committed)
            # A 3-slot block starting at slot 3 occupies 3,4,5 — slot 4 clashes.
            cand = SlotCandidate(
                instance_id=1, day_of_week=0, slot_number=3,
                start_time=time(9), end_time=time(12), faculty_id=1, room_id=1,
                student_group_id=1, subject_id=9, session_type="LECTURE",
                block_length=3,
            )
            violations = checker.check_all(cand)
            assert any(
                v.constraint == "NO_TEACHER_DOUBLE_BOOK" for v in violations
            ), violations
            # A block of another subject on non-overlapping slots is fine.
            cand2 = SlotCandidate(
                instance_id=1, day_of_week=0, slot_number=5,
                start_time=time(11), end_time=time(14), faculty_id=1, room_id=1,
                student_group_id=1, subject_id=10, session_type="LECTURE",
                block_length=3,
            )
            assert checker.is_valid(cand2), checker.check_all(cand2)
        finally:
            db.close()

    @test("OR-Tools produces a contiguous lab block")
    def t_ortools_block(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal(requires_lab=True, weekly_hours=3)
        headers = auth_headers(login_token(client))
        _add_rule(client, headers, ids["profile"], ids["subject"],
                  {"block_lengths": {str(ids["subject"]): 3}})
        slots = _gen_slots(client, headers, ids["profile"], algorithm="OR_TOOLS")
        assert len(slots) == 3, f"expected one 3-slot block, got {len(slots)} slots"
        assert len({sl["day_of_week"] for sl in slots}) == 1, slots
        assert len({sl["room_id"] for sl in slots}) == 1, slots
        nums = sorted(sl["slot_number"] for sl in slots)
        assert nums == list(range(nums[0], nums[0] + 3)), f"not contiguous: {nums}"

    @test("OR-Tools honors the block size in its domain")
    def t_ortools_size(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal(requires_lab=True, weekly_hours=6)
        headers = auth_headers(login_token(client))
        _add_rule(client, headers, ids["profile"], ids["subject"],
                  {"block_lengths": {str(ids["subject"]): 3}})
        slots = _gen_slots(client, headers, ids["profile"], algorithm="OR_TOOLS")
        assert len(slots) == 6, f"expected two 3-slot blocks, got {len(slots)}"
        # Two blocks means two distinct days, each a contiguous trio.
        by_day: dict[int, list[int]] = {}
        for sl in slots:
            by_day.setdefault(sl["day_of_week"], []).append(sl["slot_number"])
        assert len(by_day) == 2, f"expected 2 block days, got {by_day}"
        for nums in by_day.values():
            assert len(nums) == 3, nums
            assert nums == list(range(min(nums), min(nums) + 3)), f"not contiguous: {nums}"

    return [t_config, t_validator, t_time_pref_block, t_consecutive_block,
            t_greedy_block, t_greedy_remainder, t_greedy_default, t_no_rule,
            t_checker_overlap, t_ortools_block, t_ortools_size]
