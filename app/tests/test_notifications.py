"""Two-channel notifications (in-app + email) on publish and mid-year change."""
from app.tests.test_runner import suite, test, login_token, auth_headers


def _seed_publish_scenario():
    """seed_minimal + teacher/student Admins linked by email, then publish.

    Returns (ids, instance_id).
    """
    from app.tests.test_runner import seed_minimal, make_client
    from app.tests.conftest import TestingSessionLocal
    from app.models.admin import Admin, AdminRole
    from app.models.groups import StudentGroup
    from app.utils.auth import hash_password

    ids = seed_minimal()
    db = TestingSessionLocal()
    try:
        # Alice the faculty has a teacher account; the group links a student.
        db.add(Admin(email="alice@x.com", name="Alice Teacher",
                     password=hash_password("teach123"),
                     role=AdminRole.TEACHER))
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
    return ids, inst["id"], client, headers


@suite("Phase 5 — Notifications (in-app + email)")
def _phase5_notifications(s):
    @test("publishing creates in-app notifications for the relevant admins")
    def t_publish_rows(client):
        ids, inst_id, c, headers = _seed_publish_scenario()
        pub = c.post(f"/instances/{inst_id}/publish", headers=headers)
        assert pub.status_code == 200, pub.text

        # Admin (college tier), the teacher (faculty link), the student
        # (group link) all get a PUBLISH row.
        admin_headers = auth_headers(login_token(client))
        rows = c.get("/notifications", headers=admin_headers).json()
        assert any(r["kind"] == "PUBLISH" and r["instance_id"] == inst_id for r in rows), rows

        teacher_headers = auth_headers(login_token(client, email="alice@x.com", password="teach123"))
        t_rows = c.get("/notifications", headers=teacher_headers).json()
        assert any(r["kind"] == "PUBLISH" and r["instance_id"] == inst_id for r in t_rows), t_rows

        student_headers = auth_headers(login_token(client, email="s@x.com", password="stud123"))
        s_rows = c.get("/notifications", headers=student_headers).json()
        assert any(r["kind"] == "PUBLISH" and r["instance_id"] == inst_id for r in s_rows), s_rows

    @test("unread-count and mark-read work per recipient")
    def t_read_flow(client):
        ids, inst_id, c, headers = _seed_publish_scenario()
        c.post(f"/instances/{inst_id}/publish", headers=headers)
        teacher_headers = auth_headers(login_token(client, email="alice@x.com", password="teach123"))

        count = c.get("/notifications/unread-count", headers=teacher_headers).json()
        assert count["unread"] >= 1, count

        rows = c.get("/notifications", headers=teacher_headers).json()
        target = next(r for r in rows if r["kind"] == "PUBLISH")
        r = c.post(f"/notifications/{target['id']}/read", headers=teacher_headers)
        assert r.status_code == 200, r.text
        assert r.json()["is_read"] is True

        count2 = c.get("/notifications/unread-count", headers=teacher_headers).json()
        assert count2["unread"] == max(0, count["unread"] - 1), count2

        marked = c.post("/notifications/read-all", headers=teacher_headers).json()
        assert marked["marked"] == count2["unread"], marked
        count3 = c.get("/notifications/unread-count", headers=teacher_headers).json()
        assert count3["unread"] == 0, count3

    @test("a mid-year change creates CHANGE notifications")
    def t_change_rows(client):
        ids, inst_id, c, headers = _seed_publish_scenario()
        c.post(f"/instances/{inst_id}/publish", headers=headers)
        slots = c.get(f"/instances/{inst_id}/slots", headers=headers).json()
        target = slots[0]

        from app.tests.conftest import TestingSessionLocal
        from app.models.faculty import Faculty
        db = TestingSessionLocal()
        try:
            bob = Faculty(name="Bob", email="bob@x.com", department="CS",
                          max_hours_per_week=20, max_hours_per_day=6)
            db.add(bob)
            db.commit()
            ids["bob"] = bob.id
        finally:
            db.close()

        r = c.post(f"/instances/{inst_id}/overrides", headers=headers, json={
            "slot_id": target["id"], "override_type": "TEACHER_COVER",
            "new_faculty_id": ids["bob"], "reason": "cover",
        })
        assert r.status_code == 201, r.text

        admin_headers = auth_headers(login_token(client))
        rows = c.get("/notifications?unread_only=true", headers=admin_headers).json()
        assert any(r["kind"] == "CHANGE" for r in rows), rows

    @test("notifications are scoped to the recipient")
    def t_scoping(client):
        from app.tests.test_runner import seed_minimal
        from app.tests.conftest import TestingSessionLocal
        from app.models.admin import Admin, AdminRole
        from app.utils.auth import hash_password
        seed_minimal()
        db = TestingSessionLocal()
        try:
            db.add(Admin(email="bob@x.com", name="Bob Teacher",
                         password=hash_password("teach123"),
                         role=AdminRole.TEACHER))
            db.commit()
        finally:
            db.close()
        # Bob has no notifications (nothing published referencing him).
        b_headers = auth_headers(login_token(client, email="bob@x.com", password="teach123"))
        rows = client.get("/notifications", headers=b_headers).json()
        assert rows == [], rows

    return [t_publish_rows, t_read_flow, t_change_rows, t_scoping]
