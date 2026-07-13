"""Phase 1 tests: /health, /settings, /assignments, scheduler feature flag."""
from app.tests.test_runner import suite, test, seed_minimal


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
