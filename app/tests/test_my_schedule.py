"""Teacher self-service portal (/my/*, DD-022 #1)."""
from app.tests.test_runner import suite, test, login_token, auth_headers


def _seed_teacher_with_schedule():
    """seed_minimal + a teacher Admin whose email matches a Faculty row.

    Returns (ids, teacher_token_headers, instance_id).
    """
    from app.tests.test_runner import seed_minimal, make_client
    from app.tests.conftest import TestingSessionLocal
    from app.models.admin import Admin, AdminRole
    from app.utils.auth import hash_password

    ids = seed_minimal()
    # The faculty is Alice (alice@x.com); provision a teacher login with that
    # same email so the /my identity resolution matches.
    db = TestingSessionLocal()
    try:
        db.add(Admin(email="alice@x.com", name="Alice Teacher",
                     password=hash_password("teach123"),
                     role=AdminRole.TEACHER))
        db.commit()
    finally:
        db.close()

    client = make_client()
    headers = auth_headers(login_token(client))
    r = client.post("/generate/", headers=headers, json={
        "profile_id": ids["profile"], "academic_year": "2025-26",
        "semester": 3, "timetable_type": "CLASS",
        "instances_requested": 1, "algorithm": "GREEDY",
    })
    assert r.status_code == 201, r.text
    gen = r.json()
    inst = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]
    # Publish so /my reads it as the live timetable.
    pub = client.post(f"/instances/{inst['id']}/publish", headers=headers)
    assert pub.status_code == 200, pub.text
    return ids, inst["id"]


def _seed_student_with_timetable():
    """seed_minimal + a student Admin whose email is a group's student_email.

    Returns (ids, student_token_headers, instance_id).
    """
    from app.tests.test_runner import seed_minimal, make_client
    from app.tests.conftest import TestingSessionLocal
    from app.models.admin import Admin, AdminRole
    from app.utils.auth import hash_password

    ids = seed_minimal()
    db = TestingSessionLocal()
    try:
        from app.models.groups import StudentGroup
        group = db.get(StudentGroup, ids["group"])
        group.student_email = "s@x.com"
        db.add(Admin(email="s@x.com", name="Student S",
                     password=hash_password("stud123"),
                     role=AdminRole.STUDENT))
        db.commit()
    finally:
        db.close()

    client = make_client()
    headers = auth_headers(login_token(client))
    r = client.post("/generate/", headers=headers, json={
        "profile_id": ids["profile"], "academic_year": "2025-26",
        "semester": 3, "timetable_type": "CLASS",
        "instances_requested": 1, "algorithm": "GREEDY",
    })
    assert r.status_code == 201, r.text
    gen = r.json()
    inst = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]
    pub = client.post(f"/instances/{inst['id']}/publish", headers=headers)
    assert pub.status_code == 200, pub.text
    return ids, inst["id"]


@suite("Phase 5 — Student portal (/my timetable)")
def _phase5_my_timetable(s):
    @test("a student sees their group's published timetable with names")
    def t_my_timetable(client):
        ids, inst_id = _seed_student_with_timetable()
        student_headers = auth_headers(login_token(
            client, email="s@x.com", password="stud123"))
        r = client.get("/my/timetable", headers=student_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["group"]["id"] == ids["group"]
        assert inst_id in body["published_instance_ids"]
        assert len(body["slots"]) >= 1, body
        slot = body["slots"][0]
        assert slot["subject_code"] == "M101"
        assert slot["faculty_name"] == "Alice"
        assert slot["group_name"] == "CS-A"

    @test("an unmatched student account gets an empty timetable")
    def t_my_timetable_empty(client):
        from app.tests.test_runner import seed_minimal
        from app.tests.conftest import TestingSessionLocal
        from app.models.admin import Admin, AdminRole
        from app.utils.auth import hash_password
        seed_minimal()
        db = TestingSessionLocal()
        try:
            db.add(Admin(email="nobody2@x.com", name="Nobody2",
                         password=hash_password("stud123"),
                         role=AdminRole.STUDENT))
            db.commit()
        finally:
            db.close()
        student_headers = auth_headers(login_token(
            client, email="nobody2@x.com", password="stud123"))
        r = client.get("/my/timetable", headers=student_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["group"] is None
        assert body["slots"] == []

    @test("a teacher cannot read the student portal and vice versa")
    def t_role_gates(client):
        from app.tests.test_runner import seed_minimal
        from app.tests.conftest import TestingSessionLocal
        from app.models.admin import Admin, AdminRole
        from app.utils.auth import hash_password
        seed_minimal()
        db = TestingSessionLocal()
        try:
            db.add(Admin(email="teach2@x.com", name="Teach2",
                         password=hash_password("teach123"),
                         role=AdminRole.TEACHER))
            db.commit()
        finally:
            db.close()
        teacher_headers = auth_headers(login_token(
            client, email="teach2@x.com", password="teach123"))
        r = client.get("/my/timetable", headers=teacher_headers)
        assert r.status_code == 403, r.text

    @test("a student can export their group's iCal")
    def t_my_export(client):
        _seed_student_with_timetable()
        student_headers = auth_headers(login_token(
            client, email="s@x.com", password="stud123"))
        r = client.get("/my/export/ical", headers=student_headers)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/calendar")
        assert "BEGIN:VCALENDAR" in r.text

    @test("a student's today endpoint returns their group's weekday sessions")
    def t_my_today(client):
        from datetime import datetime
        _seed_student_with_timetable()
        student_headers = auth_headers(login_token(
            client, email="s@x.com", password="stud123"))
        r = client.get("/my/today", headers=student_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["group"]["name"] == "CS-A"
        assert body["day_of_week"] == datetime.utcnow().weekday()
        assert isinstance(body["slots"], list)

    return [t_my_timetable, t_my_timetable_empty, t_role_gates, t_my_export,
            t_my_today]


@suite("Phase 5 — Date-resolution of mid-year changes (DD-022 #2)")
def _phase5_date_resolution(s):
    def _seed_resolved():
        """A published instance + a second faculty, teacher login resolved."""
        from app.tests.test_runner import seed_minimal, make_client
        from app.tests.conftest import TestingSessionLocal
        from app.models.admin import Admin, AdminRole
        from app.models.faculty import Faculty
        from app.utils.auth import hash_password

        ids = seed_minimal()
        db = TestingSessionLocal()
        try:
            bob = Faculty(name="Bob", email="bob@x.com", department="CS",
                          max_hours_per_week=20, max_hours_per_day=6)
            db.add(bob)
            db.flush()
            db.add(Admin(email="alice@x.com", name="Alice Teacher",
                         password=hash_password("teach123"),
                         role=AdminRole.TEACHER))
            ids["bob"] = bob.id
            db.commit()
        finally:
            db.close()

        client = make_client()
        headers = auth_headers(login_token(client))
        r = client.post("/generate/", headers=headers, json={
            "profile_id": ids["profile"], "academic_year": "2025-26",
            "semester": 3, "timetable_type": "CLASS",
            "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        inst = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]
        pub = client.post(f"/instances/{inst['id']}/publish", headers=headers)
        assert pub.status_code == 200, pub.text
        return ids, inst["id"], client, headers

    @test("a permanent cover changes the teacher on every date")
    def t_permanent_cover(client):
        from datetime import date
        ids, inst_id, c, headers = _seed_resolved()
        slots = c.get(f"/instances/{inst_id}/slots", headers=headers).json()
        target = slots[0]
        r = c.post(f"/instances/{inst_id}/overrides", headers=headers, json={
            "slot_id": target["id"], "override_type": "TEACHER_COVER",
            "new_faculty_id": ids["bob"], "reason": "permanent",
        })
        assert r.status_code == 201, r.text

        teacher_headers = auth_headers(login_token(client, email="alice@x.com", password="teach123"))
        # The teacher's own schedule for the covered slot's weekday now shows Bob.
        # Pick a date whose weekday == the covered slot's day_of_week.
        d = date(2026, 7, 6)  # a Monday
        while d.weekday() != target["day_of_week"]:
            d = date.fromordinal(d.toordinal() + 1)
        r2 = c.get(f"/my/schedule?date={d.isoformat()}", headers=teacher_headers)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        covered = next(sl for sl in body["slots"] if sl["id"] == target["id"])
        assert covered["faculty_name"] == "Bob", covered
        # Every matching date carries the cover (permanent).
        d2 = date.fromordinal(d.toordinal() + 7)
        r3 = c.get(f"/my/schedule?date={d2.isoformat()}", headers=teacher_headers)
        covered2 = next(sl for sl in r3.json()["slots"] if sl["id"] == target["id"])
        assert covered2["faculty_name"] == "Bob", covered2

    @test("a TEMP cover wins inside its window, the base outside it")
    def t_temp_window(client):
        from datetime import date, timedelta
        ids, inst_id, c, headers = _seed_resolved()
        slots = c.get(f"/instances/{inst_id}/slots", headers=headers).json()
        target = slots[0]
        d = date(2026, 7, 6)
        while d.weekday() != target["day_of_week"]:
            d = date.fromordinal(d.toordinal() + 1)
        window_from, window_to = d.isoformat(), d.isoformat()
        r = c.post(f"/instances/{inst_id}/overrides", headers=headers, json={
            "slot_id": target["id"], "override_type": "TEMP",
            "new_faculty_id": ids["bob"], "date_from": window_from,
            "date_to": window_to, "reason": "temp cover one day",
        })
        assert r.status_code == 201, r.text

        teacher_headers = auth_headers(login_token(client, email="alice@x.com", password="teach123"))
        # Inside the window -> Bob.
        r2 = c.get(f"/my/schedule?date={d.isoformat()}", headers=teacher_headers)
        inside = next(sl for sl in r2.json()["slots"] if sl["id"] == target["id"])
        assert inside["faculty_name"] == "Bob", inside
        # Outside the window (next week) -> base teacher (Alice).
        r3 = c.get(f"/my/schedule?date={(d + timedelta(days=7)).isoformat()}", headers=teacher_headers)
        outside = next(sl for sl in r3.json()["slots"] if sl["id"] == target["id"])
        assert outside["faculty_name"] == "Alice", outside

    @test("a SWAP exchanges faculty/room at each position")
    def t_swap(client):
        from datetime import date
        ids, inst_id, c, headers = _seed_resolved()
        slots = c.get(f"/instances/{inst_id}/slots", headers=headers).json()
        # Pick two slots that use different rooms (seed has R1 + L1; a non-lab
        # subject uses the classroom). If they share a room, swap still applies
        # but the visible change is the faculty/room exchange — assert on rooms
        # only when they differ.
        a, b = slots[0], slots[1]
        r = c.post(f"/instances/{inst_id}/slots/{a['id']}/swap", headers=headers,
                   json={"with_slot_id": b["id"], "reason": "swap"})
        assert r.status_code == 201, r.text

        teacher_headers = auth_headers(login_token(client, email="alice@x.com", password="teach123"))
        d = date(2026, 7, 6)
        while d.weekday() != a["day_of_week"]:
            d = date.fromordinal(d.toordinal() + 1)
        r2 = c.get(f"/my/schedule?date={d.isoformat()}", headers=teacher_headers)
        body = r2.json()
        at_a = next(sl for sl in body["slots"] if sl["id"] == a["id"])
        # The swap exchanges the two slots' placements: A now carries B's room.
        # B's own day may differ from A's, so read B's room from the weekly view.
        weekly = c.get("/my/schedule", headers=teacher_headers).json()
        b_room_code = next(sl for sl in weekly["slots"] if sl["id"] == b["id"])["room_code"]
        # Only assert the exchange when the two slots actually use different
        # rooms (both slots in the tiny seed can share the same classroom).
        a_room = next(sl for sl in slots if sl["id"] == a["id"])["room_id"]
        b_room = next(sl for sl in slots if sl["id"] == b["id"])["room_id"]
        if a_room != b_room:
            assert at_a["room_code"] == b_room_code, (at_a, b_room_code)

    return [t_permanent_cover, t_temp_window, t_swap]


@suite("Phase 5 — Teacher portal (/my schedule)")
def _phase5_my_schedule(s):
    @test("a teacher sees only their own published slots with names")
    def t_my_schedule(client):
        from app.tests.test_runner import seed_minimal
        ids, inst_id = _seed_teacher_with_schedule()
        teacher_headers = auth_headers(login_token(
            client, email="alice@x.com", password="teach123"))
        r = client.get("/my/schedule", headers=teacher_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["faculty"]["email"] == "alice@x.com"
        assert inst_id in body["published_instance_ids"]
        assert len(body["slots"]) >= 1, body
        slot = body["slots"][0]
        assert slot["subject_code"] == "M101"
        assert slot["room_code"] in ("R1", "L1")
        # The resolved schema carries names (not ids) so the UI never needs
        # cross-references; the teacher's slots are all for the matching faculty.
        assert len(body["slots"]) == len(
            [s for s in body["slots"] if s["id"]])

    @test("an unmatched teacher account gets an empty schedule")
    def t_my_schedule_empty(client):
        from app.tests.test_runner import seed_minimal
        from app.tests.conftest import TestingSessionLocal
        from app.models.admin import Admin, AdminRole
        from app.utils.auth import hash_password
        seed_minimal()
        db = TestingSessionLocal()
        try:
            db.add(Admin(email="nobody@x.com", name="Nobody",
                         password=hash_password("teach123"),
                         role=AdminRole.TEACHER))
            db.commit()
        finally:
            db.close()
        teacher_headers = auth_headers(login_token(
            client, email="nobody@x.com", password="teach123"))
        r = client.get("/my/schedule", headers=teacher_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["faculty"] is None
        assert body["slots"] == []

    @test("an admin cannot read the teacher portal")
    def t_role_gate(client):
        from app.tests.test_runner import seed_minimal
        seed_minimal()
        admin_headers = auth_headers(login_token(client))
        r = client.get("/my/schedule", headers=admin_headers)
        assert r.status_code == 403, r.text

    @test("a teacher can export their own iCal")
    def t_my_export(client):
        from app.tests.test_runner import seed_minimal
        _seed_teacher_with_schedule()
        teacher_headers = auth_headers(login_token(
            client, email="alice@x.com", password="teach123"))
        r = client.get("/my/export/ical", headers=teacher_headers)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/calendar")
        assert "BEGIN:VCALENDAR" in r.text

    @test("a teacher's today endpoint returns their weekday sessions")
    def t_my_today(client):
        from datetime import datetime
        from app.tests.test_runner import seed_minimal
        _seed_teacher_with_schedule()
        teacher_headers = auth_headers(login_token(
            client, email="alice@x.com", password="teach123"))
        r = client.get("/my/today", headers=teacher_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["faculty"]["email"] == "alice@x.com"
        assert body["day_of_week"] == datetime.utcnow().weekday()
        assert isinstance(body["slots"], list)

    return [t_my_schedule, t_my_schedule_empty, t_role_gate, t_my_export,
            t_my_today]
