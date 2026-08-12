"""Mid-year change loop: timetable_overrides endpoints (DD-026)."""
from app.tests.test_runner import suite, test, seed_minimal, login_token, auth_headers


def _seed_with_second_faculty():
    """seed_minimal + a second (free) teacher, plus a published instance.

    Returns (ids, instance_id, slots).
    """
    from app.tests.test_runner import reset_db, create_admin, ensure_settings
    from app.tests.conftest import TestingSessionLocal
    from app.models.faculty import Faculty

    ids = seed_minimal()
    db = TestingSessionLocal()
    try:
        bob = Faculty(name="Bob", email="bob@x.com", department="CS",
                      max_hours_per_week=20, max_hours_per_day=6)
        db.add(bob)
        db.commit()
        ids["bob"] = bob.id
    finally:
        db.close()

    client, headers = _client_and_headers()
    r = client.post("/generate/", headers=headers, json={
        "profile_id": ids["profile"], "academic_year": "2025-26",
        "semester": 3, "timetable_type": "CLASS",
        "instances_requested": 1, "algorithm": "GREEDY",
    })
    assert r.status_code == 201, r.text
    gen = r.json()
    inst = client.get(f"/instances/{gen['id']}", headers=headers).json()[0]
    slots = client.get(f"/instances/{inst['id']}/slots", headers=headers).json()
    return ids, inst["id"], slots


def _client_and_headers():
    from app.tests.test_runner import make_client
    client = make_client()
    return client, auth_headers(login_token(client))


@suite("Phase 5 — Mid-year change loop (timetable_overrides)")
def _phase5_overrides(s):
    @test("a teacher cover is recorded and validated clean")
    def t_cover_valid(client):
        ids, inst_id, slots = _seed_with_second_faculty()
        headers = auth_headers(login_token(client))
        target = slots[0]
        r = client.post(
            f"/instances/{inst_id}/overrides", headers=headers, json={
                "slot_id": target["id"],
                "override_type": "TEACHER_COVER",
                "new_faculty_id": ids["bob"],
                "reason": "Alice left the college",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["new_faculty_id"] == ids["bob"]
        assert body["resolved_at"] is None
        # The base slot is untouched.
        r2 = client.get(f"/instances/{inst_id}/slots", headers=headers).json()
        kept = next(sl for sl in r2 if sl["id"] == target["id"])
        assert kept["faculty_id"] == ids["faculty"]

    @test("a cover that violates the new teacher's availability is rejected 409")
    def t_cover_conflict(client):
        from app.tests.conftest import TestingSessionLocal
        from app.models.faculty import FacultyAvailability, AvailabilityType
        from app.tests.test_runner import login_token, auth_headers
        ids, inst_id, slots = _seed_with_second_faculty()
        # Bob is unavailable all day on the covered slot's weekday.
        db = TestingSessionLocal()
        try:
            db.add(FacultyAvailability(
                faculty_id=ids["bob"], day_of_week=slots[0]["day_of_week"],
                availability=AvailabilityType.UNAVAILABLE,
            ))
            db.commit()
        finally:
            db.close()
        headers = auth_headers(login_token(client))
        target = slots[0]
        r = client.post(
            f"/instances/{inst_id}/overrides", headers=headers, json={
                "slot_id": target["id"],
                "override_type": "TEACHER_COVER",
                "new_faculty_id": ids["bob"],
                "reason": "cover unavailable teacher",
            },
        )
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert "Change rejected" in detail["message"]
        assert detail["violations"], detail

    @test("a room change is recorded")
    def t_room_change(client):
        ids, inst_id, slots = _seed_with_second_faculty()
        headers = auth_headers(login_token(client))
        target = slots[0]
        r = client.post(
            f"/instances/{inst_id}/overrides", headers=headers, json={
                "slot_id": target["id"],
                "override_type": "ROOM_CHANGE",
                "new_room_id": ids["classroom"],
                "reason": "lab under repair",
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["new_room_id"] == ids["classroom"]

    @test("a swap of two slots is recorded")
    def t_swap(client):
        ids, inst_id, slots = _seed_with_second_faculty()
        headers = auth_headers(login_token(client))
        a, b = slots[0], slots[1]
        r = client.post(
            f"/instances/{inst_id}/slots/{a['id']}/swap", headers=headers,
            json={"with_slot_id": b["id"], "reason": "swap Monday/Friday"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["override_type"] == "SWAP"
        assert body["swap_with_slot_id"] == b["id"]

    @test("an override can be resolved (reverted) and kept as history")
    def t_resolve(client):
        ids, inst_id, slots = _seed_with_second_faculty()
        headers = auth_headers(login_token(client))
        target = slots[0]
        r = client.post(
            f"/instances/{inst_id}/overrides", headers=headers, json={
                "slot_id": target["id"],
                "override_type": "TEACHER_COVER",
                "new_faculty_id": ids["bob"],
            },
        )
        oid = r.json()["id"]
        assert r.status_code == 201, r.text
        r2 = client.delete(f"/instances/{inst_id}/overrides/{oid}", headers=headers)
        assert r2.status_code == 204, r2.text
        active = client.get(
            f"/instances/{inst_id}/overrides?resolved=false", headers=headers).json()
        assert all(o["id"] != oid for o in active), active
        history = client.get(
            f"/instances/{inst_id}/overrides?resolved=true", headers=headers).json()
        assert any(o["id"] == oid for o in history), history

    @test("the change list resolves old/new names for display")
    def t_list_detail(client):
        ids, inst_id, slots = _seed_with_second_faculty()
        headers = auth_headers(login_token(client))
        target = slots[0]
        client.post(
            f"/instances/{inst_id}/overrides", headers=headers, json={
                "slot_id": target["id"],
                "override_type": "TEACHER_COVER",
                "new_faculty_id": ids["bob"],
                "reason": "Alice resigned",
            },
        )
        lst = client.get(f"/instances/{inst_id}/overrides", headers=headers).json()
        assert len(lst) == 1, lst
        row = lst[0]
        assert row["old_faculty_name"] == "Alice"
        assert row["new_faculty_name"] == "Bob"
        assert row["slot_day"] == target["day_of_week"]
        assert row["slot_number"] == target["slot_number"]

    @test("available-faculty lists candidates free at a (day, slot)")
    def t_available(client):
        ids, inst_id, slots = _seed_with_second_faculty()
        headers = auth_headers(login_token(client))
        target = slots[0]
        r = client.get(
            f"/instances/{inst_id}/overrides/available-faculty",
            params={"day_of_week": target["day_of_week"],
                    "slot_number": target["slot_number"]},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        names = {f["name"] for f in r.json()}
        # Alice is booked at this slot, Bob is free → Bob is a candidate,
        # Alice is not (unless excluded as the slot's own teacher).
        assert "Bob" in names, names
        assert "Alice" not in names, names

    return [t_cover_valid, t_cover_conflict, t_room_change, t_swap,
            t_resolve, t_list_detail, t_available]
