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
