"""Phase 1 tests: /health, /settings, /assignments, scheduler feature flag."""
import csv
import io

from app.tests.test_runner import suite, test, seed_minimal, seed_two_divisions


@suite("Phase 1 — Health & Settings")
def _phase1_settings(s):
    @test("health endpoint returns ok")
    def t_health(client):
        from app.tests.test_runner import reset_db, create_admin
        reset_db(); create_admin()
        r = client.get("/health")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok"
        assert body["db"] == "connected"

    @test("settings singleton is auto-created on first GET")
    def t_settings_default(client):
        from app.tests.test_runner import reset_db, create_admin, login_token, auth_headers
        reset_db(); create_admin()
        token = login_token(client)
        r = client.get("/settings/", headers=auth_headers(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enable_lab_batches"] is False
        assert body["allow_cross_dept_subjects"] is False
        assert body["enable_soft_constraint_scoring"] is True

    @test("PUT settings updates individual flags")
    def t_settings_put(client):
        from app.tests.test_runner import reset_db, create_admin, login_token, auth_headers
        reset_db(); create_admin()
        token = login_token(client)
        r = client.put(
            "/settings/",
            json={"enable_lab_batches": True, "config_json": {"max_cross_dept_per_day": 2}},
            headers=auth_headers(token),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enable_lab_batches"] is True
        assert body["config_json"] == {"max_cross_dept_per_day": 2}
        assert body["allow_cross_dept_subjects"] is False

    @test("settings endpoint requires auth")
    def t_settings_auth(client):
        from app.tests.test_runner import reset_db
        reset_db()
        r = client.get("/settings/")
        assert r.status_code in (401, 403)

    return [t_health, t_settings_default, t_settings_put, t_settings_auth]


@suite("Phase 1 — Subject Assignments CRUD")
def _phase1_assignments(s):
    @test("create assignment with valid ids")
    def t_create(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        r = client.post("/assignments/", headers=auth_headers(token), json={
            "subject_id": ids["subject"],
            "faculty_id": ids["faculty"],
            "group_id": ids["group"],
            "weekly_hours": 4,
            "load_share": 0.8,
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["weekly_hours"] == 4
        assert abs(body["load_share"] - 0.8) < 1e-9

    @test("create assignment with invalid subject 404s")
    def t_invalid(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        r = client.post("/assignments/", headers=auth_headers(token), json={
            "subject_id": 9999,
            "faculty_id": ids["faculty"],
            "group_id": ids["group"],
            "weekly_hours": 2,
        })
        assert r.status_code == 404

    @test("list and filter assignments")
    def t_list(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        r = client.get(
            f"/assignments/?subject_id={ids['subject']}",
            headers=auth_headers(token),
        )
        assert r.status_code == 200
        assert len(r.json()) == 1

    @test("update assignment changes load_share")
    def t_update(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        r = client.get("/assignments/", headers=auth_headers(token))
        a_id = r.json()[0]["id"]
        r = client.put(
            f"/assignments/{a_id}",
            headers=auth_headers(token),
            json={"load_share": 0.5, "weekly_hours": 5},
        )
        assert r.status_code == 200, r.text
        assert abs(r.json()["load_share"] - 0.5) < 1e-9
        assert r.json()["weekly_hours"] == 5

    @test("delete assignment")
    def t_delete(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        r = client.get("/assignments/", headers=auth_headers(token))
        a_id = r.json()[0]["id"]
        r = client.delete(f"/assignments/{a_id}", headers=auth_headers(token))
        assert r.status_code == 204
        r = client.get("/assignments/", headers=auth_headers(token))
        assert r.json() == []

    return [t_create, t_invalid, t_list, t_update, t_delete]


@suite("Phase 1 — Engine honors feature flags")
def _phase1_engine(s):
    @test("cross-department session is dropped when flag is OFF")
    def t_cross_off(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal(allow_cross_dept=False, cross_dept=True)
        token = login_token(client)
        r = client.post(
            "/generate/",
            headers=auth_headers(token),
            json={
                "profile_id": ids["profile"],
                "academic_year": "2025-26",
                "semester": 3,
                "timetable_type": "CLASS",
                "instances_requested": 1,
                "algorithm": "GREEDY",
            },
        )
        assert r.status_code == 201, r.text
        gen = r.json()
        r = client.get(f"/instances/{gen['id']}", headers=auth_headers(token))
        assert r.status_code == 200
        instances = r.json()
        assert len(instances) == 1
        inst_id = instances[0]["id"]
        r = client.get(f"/instances/{inst_id}/slots", headers=auth_headers(token))
        slots = r.json()
        assert slots == [], f"expected no slots, got {slots}"

    @test("cross-department session is scheduled when flag is ON")
    def t_cross_on(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal(allow_cross_dept=True, cross_dept=True)
        token = login_token(client)
        r = client.post("/generate/", headers=auth_headers(token), json={
            "profile_id": ids["profile"],
            "academic_year": "2025-26",
            "semester": 3,
            "timetable_type": "CLASS",
            "instances_requested": 1,
            "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        r = client.get(f"/instances/{gen['id']}", headers=auth_headers(token))
        inst_id = r.json()[0]["id"]
        r = client.get(f"/instances/{inst_id}/slots", headers=auth_headers(token))
        slots = r.json()
        assert len(slots) == 3, f"expected 3 slots, got {len(slots)}"

    @test("scheduler populates instances_produced (bug fix)")
    def t_bug_fix(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        r = client.post("/generate/", headers=auth_headers(token), json={
            "profile_id": ids["profile"],
            "academic_year": "2025-26",
            "semester": 3,
            "timetable_type": "CLASS",
            "instances_requested": 2,
            "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        assert gen["instances_produced"] == 2, gen
        assert gen["generation_status"] == "COMPLETED", gen

    return [t_cross_off, t_cross_on, t_bug_fix]


@suite("Phase 1 — Faculty availability date ranges")
def _phase1_availability_dates(s):
    def _gen_slots(client, headers, profile_id):
        r = client.post("/generate/", headers=headers, json={
            "profile_id": profile_id, "academic_year": "2025-26", "semester": 3,
            "timetable_type": "CLASS", "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        r = client.get(f"/instances/{gen['id']}", headers=headers)
        inst_id = r.json()[0]["id"]
        return client.get(f"/instances/{inst_id}/slots", headers=headers).json()

    @test("availability CRUD works without effective dates (data-integrity)")
    def t_crud_without_dates(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        r = client.post("/faculty_availability/", headers=headers, json={
            "faculty_id": ids["faculty"],
            "day_of_week": 0,
            "availability": "UNAVAILABLE",
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["effective_from"] is None
        assert body["effective_to"] is None

    @test("date-bounded unavailability blocks only its week")
    def t_date_window(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        # Anchor the weekly template to Mon 2025-01-06.
        r = client.post(
            f"/profiles/{ids['profile']}/parameters", headers=headers,
            json={"param_key": "term_start", "param_value": "2025-01-06",
                  "param_type": "STRING"},
        )
        assert r.status_code in (200, 201), r.text
        # Teacher unavailable all day Monday that week.
        r = client.post("/faculty_availability/", headers=headers, json={
            "faculty_id": ids["faculty"], "day_of_week": 0,
            "availability": "UNAVAILABLE",
            "effective_from": "2025-01-06", "effective_to": "2025-01-12",
        })
        assert r.status_code == 201, r.text
        avail_id = r.json()["id"]

        slots = _gen_slots(client, headers, ids["profile"])
        assert len(slots) == 3, slots
        assert all(sl["day_of_week"] != 0 for sl in slots), (
            f"Monday should be blocked, got days {[sl['day_of_week'] for sl in slots]}"
        )
        # Committed slots carry the materialized calendar date.
        assert all(sl["slot_date"] is not None for sl in slots), slots

        # Slide the window to a week that does NOT cover the term start;
        # Monday becomes schedulable again.
        r = client.put(f"/faculty_availability/{avail_id}", headers=headers, json={
            "faculty_id": ids["faculty"], "day_of_week": 0,
            "availability": "UNAVAILABLE",
            "effective_from": "2025-02-01", "effective_to": "2025-02-07",
        })
        assert r.status_code == 200, r.text
        slots2 = _gen_slots(client, headers, ids["profile"])
        assert len(slots2) == 3, slots2
        assert any(sl["day_of_week"] == 0 for sl in slots2), (
            f"Monday should be free again, got days {[sl['day_of_week'] for sl in slots2]}"
        )

    @test("timeless unavailability still blocks its weekday")
    def t_timeless(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        r = client.post("/faculty_availability/", headers=headers, json={
            "faculty_id": ids["faculty"], "day_of_week": 0,
            "availability": "UNAVAILABLE",
        })
        assert r.status_code == 201, r.text
        slots = _gen_slots(client, headers, ids["profile"])
        assert len(slots) == 3, slots
        assert all(sl["day_of_week"] != 0 for sl in slots), (
            [sl["day_of_week"] for sl in slots]
        )

    @test("_availability_window_applies semantics")
    def t_window_rule(client):
        from datetime import date
        from app.engine.constraint_checker import ConstraintChecker

        class _W:
            def __init__(self, f, t):
                self.effective_from, self.effective_to = f, t

        d = date(2025, 1, 6)
        # No bounds -> timeless.
        assert ConstraintChecker._availability_window_applies(_W(None, None), d) is True
        # Inside the window.
        assert ConstraintChecker._availability_window_applies(_W(d, date(2025, 1, 12)), d) is True
        # Outside the window.
        assert ConstraintChecker._availability_window_applies(
            _W(date(2025, 1, 13), date(2025, 1, 19)), d) is False
        # No materialized date -> a date-bounded window is inert.
        assert ConstraintChecker._availability_window_applies(_W(d, date(2025, 1, 12)), None) is False
        # Half-bounded windows are unbounded on the missing side.
        assert ConstraintChecker._availability_window_applies(_W(d, None), date(2025, 6, 1)) is True
        assert ConstraintChecker._availability_window_applies(
            _W(None, date(2024, 12, 31)), d) is False

    return [t_crud_without_dates, t_date_window, t_timeless, t_window_rule]


@suite("Phase 1 — Cross-timetable safety")
def _phase1_cross_timetable(s):
    def _generate_one(client, headers, profile_id):
        r = client.post("/generate/", headers=headers, json={
            "profile_id": profile_id,
            "academic_year": "2025-26",
            "semester": 3,
            "timetable_type": "CLASS",
            "instances_requested": 1,
            "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        r = client.get(f"/instances/{gen['id']}", headers=headers)
        inst_id = r.json()[0]["id"]
        r = client.get(f"/instances/{inst_id}/slots", headers=headers)
        return inst_id, r.json()

    def _time_keys(slots):
        return {
            (s["faculty_id"], s["day_of_week"], s["slot_number"]) for s in slots
        }

    @test("published slots block the same teacher/time on the next run")
    def t_no_reuse(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)

        first_inst, first_slots = _generate_one(client, headers, ids["profile"])
        assert len(first_slots) == 3, first_slots

        r = client.post(f"/instances/{first_inst}/publish", headers=headers)
        assert r.status_code == 200, r.text

        _second_inst, second_slots = _generate_one(client, headers, ids["profile"])
        assert len(second_slots) == 3, second_slots

        # The regenerated timetable must not reuse any (faculty, day, slot)
        # already committed by the published one.
        assert _time_keys(first_slots).isdisjoint(_time_keys(second_slots)), (
            f"published={_time_keys(first_slots)} "
            f"reused in second={_time_keys(second_slots)}"
        )

    return [t_no_reuse]


@suite("Phase 1 — Engine flexibility & limits")
def _phase1_flexibility(s):
    def _generate_slots(client, headers, profile_id, instances=1):
        r = client.post("/generate/", headers=headers, json={
            "profile_id": profile_id,
            "academic_year": "2025-26",
            "semester": 3,
            "timetable_type": "CLASS",
            "instances_requested": instances,
            "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        r = client.get(f"/instances/{gen['id']}", headers=headers)
        inst_id = r.json()[0]["id"]
        return client.get(f"/instances/{inst_id}/slots", headers=headers).json()

    @test("day_start_time param shifts the first slot")
    def t_day_start(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        # Override the day start to 08:00 for this profile.
        r = client.post(
            f"/profiles/{ids['profile']}/parameters",
            headers=headers,
            json={"param_key": "day_start_time", "param_value": "08:00",
                  "param_type": "STRING"},
        )
        assert r.status_code in (200, 201), r.text
        slots = _generate_slots(client, headers, ids["profile"])
        assert slots, "expected slots"
        earliest = min(s["start_time"] for s in slots)
        assert earliest.startswith("08:00"), earliest

    @test("faculty weekly max-hours cap limits placed sessions")
    def t_faculty_cap(client):
        from app.tests.test_runner import login_token, auth_headers
        # Assignment asks for 3 weekly hours but the teacher is capped at 2.
        ids = seed_minimal(faculty_max_per_week=2)
        token = login_token(client)
        headers = auth_headers(token)
        slots = _generate_slots(client, headers, ids["profile"])
        assert len(slots) == 2, f"expected 2 (weekly cap), got {len(slots)}"

    return [t_day_start, t_faculty_cap]


@suite("Phase 2 — Dynamic constraint registry")
def _phase2_registry(s):
    def _gen_slots(client, headers, profile_id):
        r = client.post("/generate/", headers=headers, json={
            "profile_id": profile_id, "academic_year": "2025-26", "semester": 3,
            "timetable_type": "CLASS", "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        r = client.get(f"/instances/{gen['id']}", headers=headers)
        inst_id = r.json()[0]["id"]
        return client.get(f"/instances/{inst_id}/slots", headers=headers).json()

    @test("SUBJECT_TIME_PREFERENCE forces the subject into early slots (end to end)")
    def t_time_pref(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        r = client.post("/constraints/hard", headers=headers, json={
            "profile_id": ids["profile"],
            "constraint_type": "SUBJECT_TIME_PREFERENCE",
            "config_json": {"subject_id": ids["subject"], "max_slot": 1},
        })
        assert r.status_code == 201, r.text
        slots = _gen_slots(client, headers, ids["profile"])
        assert slots, "expected slots"
        assert all(s["slot_number"] <= 1 for s in slots), [s["slot_number"] for s in slots]

    @test("MAX_CONSECUTIVE_SAME_TEACHER validator caps a back-to-back run")
    def t_consecutive(client):
        from datetime import time
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY
        from app.engine.constraint_checker import SlotCandidate

        class _Slot:
            def __init__(self, fid, day, sn):
                self.faculty_id, self.day_of_week, self.slot_number = fid, day, sn

        committed = [_Slot(1, 0, 1), _Slot(1, 0, 2)]
        cand = SlotCandidate(
            instance_id=1, day_of_week=0, slot_number=3,
            start_time=time(9), end_time=time(10), faculty_id=1, room_id=1,
            student_group_id=1, subject_id=1, session_type="LECTURE",
        )
        v = HARD_CONSTRAINT_REGISTRY["MAX_CONSECUTIVE_SAME_TEACHER"]
        assert v(cand, committed, {"max": 2}, None) is not None   # run of 3 > 2
        assert v(cand, committed, {"max": 3}, None) is None        # exactly 3 ok

    @test("TEACHER_YEAR_RESTRICTION validator blocks disallowed years")
    def t_year(client):
        from datetime import time
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY
        from app.engine.constraint_checker import SlotCandidate

        class _Group:
            def __init__(self, year): self.year = year

        class _Ctx:
            def __init__(self, year): self._year = year
            def group(self, gid): return _Group(self._year)

        cand = SlotCandidate(
            instance_id=1, day_of_week=0, slot_number=1,
            start_time=time(9), end_time=time(10), faculty_id=7, room_id=1,
            student_group_id=1, subject_id=1, session_type="LECTURE",
        )
        v = HARD_CONSTRAINT_REGISTRY["TEACHER_YEAR_RESTRICTION"]
        cfg = {"faculty_id": 7, "allowed_years": [3, 4]}
        assert v(cand, [], cfg, _Ctx(2)) is not None   # year 2 disallowed
        assert v(cand, [], cfg, _Ctx(3)) is None         # year 3 allowed

    return [t_time_pref, t_consecutive, t_year]


@suite("Phase 3 — Soft-constraint scoring")
def _phase3_scoring(s):
    def _generate(client, headers, profile_id):
        r = client.post("/generate/", headers=headers, json={
            "profile_id": profile_id, "academic_year": "2025-26", "semester": 3,
            "timetable_type": "CLASS", "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        return r.json()

    @test("no soft rules leaves soft_score unset")
    def t_no_rules(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        gen = _generate(client, headers, ids["profile"])
        assert gen["score_best_instance"] is None, gen
        r = client.get(f"/instances/{gen['id']}", headers=headers)
        assert r.json()[0]["soft_score"] is None

    @test("a soft rule populates soft_score and the best score")
    def t_scored(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        r = client.post("/constraints/soft", headers=headers, json={
            "profile_id": ids["profile"],
            "constraint_type": "TEACHER_PREFERS_MORNING",
            "config_json": {"boundary_slot": 3},
            "weight": 2.0,
        })
        assert r.status_code == 201, r.text
        gen = _generate(client, headers, ids["profile"])
        assert gen["score_best_instance"] is not None, gen
        assert 0.0 <= gen["score_best_instance"] <= 1.0, gen
        inst = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]
        assert inst["soft_score"] is not None
        assert 0.0 <= inst["soft_score"] <= 1.0

    @test("MINIMIZE_STUDENT_FREE_SLOTS penalises gaps")
    def t_gaps(client):
        from app.engine.scorer import SOFT_CONSTRAINT_REGISTRY

        class _S:
            def __init__(self, gid, day, sn):
                self.student_group_id, self.day_of_week, self.slot_number = gid, day, sn

        # group 1, day 0, slots 1,2,4 -> span 4, 1 gap -> 1 - 1/4 = 0.75
        slots = [_S(1, 0, 1), _S(1, 0, 2), _S(1, 0, 4)]
        score = SOFT_CONSTRAINT_REGISTRY["MINIMIZE_STUDENT_FREE_SLOTS"](slots, None, None)
        assert abs(score - 0.75) < 1e-9, score
        # contiguous -> perfect
        tight = [_S(1, 0, 1), _S(1, 0, 2), _S(1, 0, 3)]
        assert SOFT_CONSTRAINT_REGISTRY["MINIMIZE_STUDENT_FREE_SLOTS"](tight, None, None) == 1.0

    @test("TEACHER_PREFERS_MORNING scores the morning fraction")
    def t_morning(client):
        from app.engine.scorer import SOFT_CONSTRAINT_REGISTRY

        class _F:
            def __init__(self, fid, sn):
                self.faculty_id, self.slot_number = fid, sn

        slots = [_F(1, 1), _F(1, 2), _F(1, 5), _F(1, 6)]  # 2 of 4 <= slot 4
        score = SOFT_CONSTRAINT_REGISTRY["TEACHER_PREFERS_MORNING"](slots, {"boundary_slot": 4}, None)
        assert abs(score - 0.5) < 1e-9, score

    return [t_no_rules, t_scored, t_gaps, t_morning]


@suite("Phase 2 — Recurring blackouts & lab rotation")
def _phase2_recurring(s):
    @test("recurring room blackout keeps that room off its weekday")
    def t_recurring_blackout(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        # The classroom is the only room big enough for the group; black it out
        # all day every Monday (day 0).
        r = client.post("/blackouts/", headers=headers, json={
            "room_id": ids["classroom"], "day_of_week": 0,
        })
        assert r.status_code == 201, r.text
        r = client.post("/generate/", headers=headers, json={
            "profile_id": ids["profile"], "academic_year": "2025-26",
            "semester": 3, "timetable_type": "CLASS",
            "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        inst_id = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]["id"]
        slots = client.get(f"/instances/{inst_id}/slots", headers=headers).json()
        assert slots, "expected sessions on other days"
        assert all(sl["day_of_week"] != 0 for sl in slots), (
            f"classroom blacked out Monday but got {[sl['day_of_week'] for sl in slots]}"
        )

    @test("blackout requires a date or a weekday")
    def t_blackout_validation(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        r = client.post("/blackouts/", headers=headers, json={"room_id": ids["classroom"]})
        assert r.status_code == 422, r.text

    @test("LAB_BATCH_ROTATION validator pins a group to its weekdays")
    def t_lab_rotation(client):
        from datetime import time
        from app.engine.constraint_registry import HARD_CONSTRAINT_REGISTRY
        from app.engine.constraint_checker import SlotCandidate

        def _cand(day):
            return SlotCandidate(
                instance_id=1, day_of_week=day, slot_number=1,
                start_time=time(9), end_time=time(10), faculty_id=1, room_id=1,
                student_group_id=11, subject_id=1, session_type="LAB",
            )

        v = HARD_CONSTRAINT_REGISTRY["LAB_BATCH_ROTATION"]
        cfg = {"group_days": {"11": [0]}}  # group 11 only on Monday
        assert v(_cand(1), [], cfg, None) is not None   # Tuesday blocked
        assert v(_cand(0), [], cfg, None) is None         # Monday allowed

    return [t_recurring_blackout, t_blackout_validation, t_lab_rotation]


@suite("Phase 3 — OR-Tools CP-SAT solver")
def _phase3_ortools(s):
    def _gen(client, headers, profile_id, algorithm):
        r = client.post("/generate/", headers=headers, json={
            "profile_id": profile_id, "academic_year": "2025-26", "semester": 3,
            "timetable_type": "CLASS", "instances_requested": 1, "algorithm": algorithm,
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        inst_id = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]["id"]
        return client.get(f"/instances/{inst_id}/slots", headers=headers).json()

    @test("OR-Tools produces a complete, conflict-free timetable")
    def t_ortools_basic(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        slots = _gen(client, headers, ids["profile"], "OR_TOOLS")
        assert len(slots) == 3, f"expected 3 sessions, got {len(slots)}"
        # same subject on distinct days, no teacher slot clash
        days = [sl["day_of_week"] for sl in slots]
        assert len(set(days)) == 3, days
        seen = set()
        for sl in slots:
            key = (sl["faculty_id"], sl["day_of_week"], sl["slot_number"])
            assert key not in seen, f"teacher double-booked: {key}"
            seen.add(key)

    @test("OR-Tools honors a hard registry constraint")
    def t_ortools_registry(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        r = client.post("/constraints/hard", headers=headers, json={
            "profile_id": ids["profile"],
            "constraint_type": "SUBJECT_TIME_PREFERENCE",
            "config_json": {"subject_id": ids["subject"], "max_slot": 1},
        })
        assert r.status_code == 201, r.text
        slots = _gen(client, headers, ids["profile"], "OR_TOOLS")
        assert slots, "expected slots"
        assert all(sl["slot_number"] <= 1 for sl in slots), [sl["slot_number"] for sl in slots]

    @test("OR-Tools pursues the TEACHER_PREFERS_MORNING soft objective")
    def t_ortools_soft_objective(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        r = client.post("/constraints/soft", headers=headers, json={
            "profile_id": ids["profile"],
            "constraint_type": "TEACHER_PREFERS_MORNING",
            "config_json": {"boundary_slot": 1},
            "weight": 1.0,
        })
        assert r.status_code == 201, r.text
        gen = client.post("/generate/", headers=headers, json={
            "profile_id": ids["profile"], "academic_year": "2025-26", "semester": 3,
            "timetable_type": "CLASS", "instances_requested": 1, "algorithm": "OR_TOOLS",
        })
        assert gen.status_code == 201, gen.text
        gen_id = gen.json()["id"]
        inst = client.get(f"/instances/{gen_id}", headers=headers).json()[0]
        slots = client.get(f"/instances/{inst['id']}/slots", headers=headers).json()
        assert slots, "expected slots"
        # The morning preference should pin every session to slot 1.
        assert all(sl["slot_number"] == 1 for sl in slots), (
            [sl["slot_number"] for sl in slots]
        )
        # And the post-hoc score confirms a fully-satisfied soft rule.
        assert inst["soft_score"] == 1.0, inst["soft_score"]

    return [t_ortools_basic, t_ortools_registry, t_ortools_soft_objective]


@suite("Phase 3 — Instance diversity")
def _phase3_diversity(s):
    @test("requesting several instances yields non-identical timetables")
    def t_diverse(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        token = login_token(client)
        headers = auth_headers(token)
        r = client.post("/generate/", headers=headers, json={
            "profile_id": ids["profile"], "academic_year": "2025-26", "semester": 3,
            "timetable_type": "CLASS", "instances_requested": 3, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        insts = client.get(f"/instances/{gen['id']}", headers=headers).json()
        assert len(insts) == 3, insts
        signatures = set()
        for inst in insts:
            slots = client.get(
                f"/instances/{inst['id']}/slots", headers=headers
            ).json()
            signatures.add(frozenset(
                (sl["student_group_id"], sl["day_of_week"],
                 sl["slot_number"], sl["subject_id"])
                for sl in slots
            ))
        assert len(signatures) >= 2, f"instances not diverse: {len(signatures)} distinct"

    return [t_diverse]


@suite("Phase 5 — Filtered exports (PDF/CSV/iCal)")
def _phase5_exports(s):
    def _headers(client):
        from app.tests.test_runner import login_token, auth_headers
        return auth_headers(login_token(client))

    def _generate(client, headers, profile_id):
        r = client.post("/generate/", headers=headers, json={
            "profile_id": profile_id, "academic_year": "2025-26", "semester": 3,
            "timetable_type": "CLASS", "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        return client.get(f"/instances/{gen['id']}", headers=headers).json()[0]["id"]

    def _csv_rows(text):
        rows = [r for r in csv.reader(io.StringIO(text)) if r]
        return rows[0], rows[1:]

    @test("full CSV export lists every session")
    def t_csv_full(client):
        ids = seed_two_divisions()
        headers = _headers(client)
        inst = _generate(client, headers, ids["profile"])
        r = client.get(f"/export/instances/{inst}/csv", headers=headers)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers["content-type"]
        _, rows = _csv_rows(r.text)
        assert len(rows) == 4, rows

    @test("CSV filtered by group returns only that group")
    def t_csv_group(client):
        ids = seed_two_divisions()
        headers = _headers(client)
        inst = _generate(client, headers, ids["profile"])
        r = client.get(
            f"/export/instances/{inst}/csv?group_id={ids['group_a']}", headers=headers
        )
        assert r.status_code == 200, r.text
        _, rows = _csv_rows(r.text)
        assert len(rows) == 2, rows
        assert all(row[8] == "CS-A" for row in rows), rows

    @test("CSV filtered by year narrows to that year")
    def t_csv_year(client):
        ids = seed_two_divisions()
        headers = _headers(client)
        inst = _generate(client, headers, ids["profile"])
        r = client.get(f"/export/instances/{inst}/csv?year=3", headers=headers)
        assert r.status_code == 200, r.text
        _, rows = _csv_rows(r.text)
        assert len(rows) == 2, rows
        assert all(row[8] == "CS-B" for row in rows), rows

    @test("CSV filtered by faculty narrows to that teacher")
    def t_csv_faculty(client):
        ids = seed_two_divisions()
        headers = _headers(client)
        inst = _generate(client, headers, ids["profile"])
        r = client.get(
            f"/export/instances/{inst}/csv?faculty_id={ids['faculty_b']}", headers=headers
        )
        assert r.status_code == 200, r.text
        _, rows = _csv_rows(r.text)
        assert len(rows) == 2, rows
        assert all(row[6] == "Prof B" for row in rows), rows

    @test("a filter matching nothing is a 404")
    def t_empty(client):
        ids = seed_two_divisions()
        headers = _headers(client)
        inst = _generate(client, headers, ids["profile"])
        r = client.get(f"/export/instances/{inst}/csv?group_id=999999", headers=headers)
        assert r.status_code == 404

    @test("iCal export is a valid recurring calendar, filterable")
    def t_ical(client):
        ids = seed_two_divisions()
        headers = _headers(client)
        inst = _generate(client, headers, ids["profile"])
        r = client.get(f"/export/instances/{inst}/ical", headers=headers)
        assert r.status_code == 200, r.text
        assert "text/calendar" in r.headers["content-type"]
        body = r.text
        assert body.startswith("BEGIN:VCALENDAR")
        assert body.rstrip().endswith("END:VCALENDAR")
        assert body.count("BEGIN:VEVENT") == 4, body
        assert "RRULE:FREQ=WEEKLY" in body
        r2 = client.get(
            f"/export/instances/{inst}/ical?faculty_id={ids['faculty_a']}", headers=headers
        )
        assert r2.text.count("BEGIN:VEVENT") == 2

    @test("PDF export returns a real pdf")
    def t_pdf(client):
        ids = seed_two_divisions()
        headers = _headers(client)
        inst = _generate(client, headers, ids["profile"])
        r = client.get(
            f"/export/instances/{inst}/pdf?group_id={ids['group_a']}", headers=headers
        )
        assert r.status_code == 200
        assert "application/pdf" in r.headers["content-type"]
        assert r.content[:4] == b"%PDF"

    return [t_csv_full, t_csv_group, t_csv_year, t_csv_faculty, t_empty, t_ical, t_pdf]


@suite("Phase 5 — API polish (pagination & audit)")
def _phase5_polish(s):
    def _fresh(client):
        from app.tests.test_runner import (
            reset_db, create_admin, login_token, auth_headers,
        )
        reset_db(); create_admin()
        return auth_headers(login_token(client))

    def _make_room(client, headers, i):
        return client.post("/rooms/", headers=headers, json={
            "name": f"R{i}", "room_code": f"RC{i}", "room_type": "CLASSROOM",
            "capacity": 40, "building": "A",
        })

    @test("list endpoints paginate and report X-Total-Count")
    def t_pagination(client):
        headers = _fresh(client)
        for i in range(3):
            assert _make_room(client, headers, i).status_code == 201
        r = client.get("/rooms/?limit=2", headers=headers)
        assert r.status_code == 200, r.text
        assert len(r.json()) == 2
        assert r.headers.get("x-total-count") == "3", dict(r.headers)
        r2 = client.get("/rooms/?skip=2&limit=2", headers=headers)
        assert len(r2.json()) == 1

    @test("pagination limits are validated")
    def t_limit_validation(client):
        headers = _fresh(client)
        assert client.get("/rooms/?limit=0", headers=headers).status_code == 422
        assert client.get("/rooms/?limit=9999", headers=headers).status_code == 422

    @test("mutations are recorded in the audit trail with a request id")
    def t_audit(client):
        headers = _fresh(client)
        r = _make_room(client, headers, 0)
        assert r.status_code == 201, r.text
        assert r.headers.get("x-request-id"), dict(r.headers)
        entries = client.get("/audit/", headers=headers).json()
        assert any(
            e["method"] == "POST" and e["path"] == "/rooms/" and e["status_code"] == 201
            for e in entries
        ), entries

    return [t_pagination, t_limit_validation, t_audit]
