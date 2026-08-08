"""Profile-combination list + explicit resolve endpoints.

Resolution was previously invisible: ``POST /generate`` merged a combination
automatically inside the scheduler, but there was no way to list combinations
or preview what a run would schedule. This suite covers the new
``GET /profiles/combinations`` (members, weights, resolution status) and
``POST /profiles/combinations/{id}/resolve`` (the same ``ProfileResolver``
merge the scheduler uses, returned for manual preview).
"""
from app.tests.test_runner import (
    suite, test, seed_two_profiles, reset_db, create_admin, ensure_settings,
    login_token, auth_headers, TestingSessionLocal,
)


def _combine(client, headers, ids, **body):
    payload = {
        "profile_ids": [ids["profile_a"], ids["profile_b"]],
        **body,
    }
    r = client.post("/profiles/combine", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@suite("Phase 4 — Profile combination list & resolve")
def _phase4_combinations_router(s):

    @test("combinations are listed with member names, weights and status")
    def t_list(client):
        ids = seed_two_profiles()
        headers = auth_headers(login_token(client))
        combo_id = _combine(client, headers, ids, name="Dept combined",
                            weights=[1.0, 2.0])
        r = client.get("/profiles/combinations", headers=headers)
        assert r.status_code == 200, r.text
        combos = r.json()
        assert len(combos) == 1, combos
        combo = combos[0]
        assert combo["id"] == combo_id, combo
        assert combo["name"] == "Dept combined", combo
        assert combo["resolution_status"] == "RESOLVABLE", combo
        by_id = {m["profile_id"]: m for m in combo["members"]}
        assert set(by_id) == {ids["profile_a"], ids["profile_b"]}, combo
        assert by_id[ids["profile_a"]]["profile_name"] == "Profile A", combo
        assert by_id[ids["profile_a"]]["weight"] == 1.0, combo
        assert by_id[ids["profile_b"]]["weight"] == 2.0, combo
        assert all(m["is_active"] for m in combo["members"]), combo

    @test("archiving a member flags the combination INACTIVE_MEMBER")
    def t_inactive_flag(client):
        ids = seed_two_profiles()
        headers = auth_headers(login_token(client))
        _combine(client, headers, ids)
        r = client.delete(f"/profiles/{ids['profile_b']}", headers=headers)
        assert r.status_code == 204, r.text
        r = client.get("/profiles/combinations", headers=headers)
        combo = r.json()[0]
        assert combo["resolution_status"] == "INACTIVE_MEMBER", combo
        member = next(m for m in combo["members"]
                      if m["profile_id"] == ids["profile_b"])
        assert member["is_active"] is False, combo

    @test("resolve returns the merged profile the scheduler would consume")
    def t_resolve_merged(client):
        ids = seed_two_profiles()
        headers = auth_headers(login_token(client))
        # Give profile A a distinct param so the higher-weight member wins.
        r = client.post(f"/profiles/{ids['profile_a']}/parameters",
                        headers=headers, json={
                            "param_key": "day_start_time",
                            "param_value": "09:00", "param_type": "STRING",
                        })
        assert r.status_code in (200, 201), r.text
        r = client.post(f"/profiles/{ids['profile_b']}/parameters",
                        headers=headers, json={
                            "param_key": "day_start_time",
                            "param_value": "08:00", "param_type": "STRING",
                        })
        assert r.status_code in (200, 201), r.text
        # One member-only hard constraint must survive the merge.
        r = client.post("/constraints/hard", headers=headers, json={
            "profile_id": ids["profile_a"],
            "constraint_type": "SUBJECT_TIME_PREFERENCE",
            "config_json": {"subject_id": ids["subject_a"], "max_slot": 1},
        })
        assert r.status_code == 201, r.text
        combo_id = _combine(client, headers, ids, weights=[1.0, 2.0])

        r = client.post(f"/profiles/combinations/{combo_id}/resolve",
                        headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["combination_id"] == combo_id, body
        assert set(body["source_profile_ids"]) == {
            ids["profile_a"], ids["profile_b"]}, body
        # Weighted param collision: profile B (weight 2) wins.
        assert body["params"]["day_start_time"] == "08:00", body["params"]
        # Resources are the union of both members' sets.
        assert set(body["resources"]["ROOM"]) == {
            ids["room_a"], ids["room_b"]}, body["resources"]
        assert set(body["resources"]["FACULTY"]) == {
            ids["faculty_a"], ids["faculty_b"]}, body["resources"]
        assert set(body["resources"]["STUDENT_GROUP"]) == {
            ids["group_a"], ids["group_b"]}, body["resources"]
        assert set(body["resources"]["SUBJECT"]) == {
            ids["subject_a"], ids["subject_b"]}, body["resources"]
        # Member constraints carry through with their type and config.
        types = [c["constraint_type"]
                 for c in body["hard_constraints"]]
        assert "SUBJECT_TIME_PREFERENCE" in types, body["hard_constraints"]

    @test("resolve preview matches what a combination run schedules")
    def t_resolve_matches_generation(client):
        ids = seed_two_profiles()
        headers = auth_headers(login_token(client))
        combo_id = _combine(client, headers, ids)
        r = client.post(f"/profiles/combinations/{combo_id}/resolve",
                        headers=headers)
        assert r.status_code == 200, r.text
        resolved_subjects = set(r.json()["resources"]["SUBJECT"])

        gen = client.post("/generate/", headers=headers, json={
            "combination_id": combo_id, "academic_year": "2025-26",
            "semester": 3, "timetable_type": "CLASS",
            "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert gen.status_code == 201, gen.text
        inst = client.get(
            f"/instances/{gen.json()['id']}", headers=headers).json()[0]
        slots = client.get(
            f"/instances/{inst['id']}/slots", headers=headers).json()
        assert set(sl["subject_id"] for sl in slots) == resolved_subjects, (
            slots, resolved_subjects)

    @test("resolve 404s on an unknown combination")
    def t_resolve_unknown(client):
        seed_two_profiles()
        headers = auth_headers(login_token(client))
        r = client.post("/profiles/combinations/99999/resolve",
                        headers=headers)
        assert r.status_code == 404, r.text

    @test("resolve 404s once a member has been archived")
    def t_resolve_inactive(client):
        ids = seed_two_profiles()
        headers = auth_headers(login_token(client))
        combo_id = _combine(client, headers, ids)
        r = client.delete(f"/profiles/{ids['profile_b']}", headers=headers)
        assert r.status_code == 204, r.text
        r = client.post(f"/profiles/combinations/{combo_id}/resolve",
                        headers=headers)
        assert r.status_code == 404, r.text

    @test("an empty list is returned when no combinations exist")
    def t_list_empty(client):
        reset_db()
        create_admin()
        headers = auth_headers(login_token(client))
        r = client.get("/profiles/combinations", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json() == [], r.text

    return [t_list, t_inactive_flag, t_resolve_merged,
            t_resolve_matches_generation, t_resolve_unknown,
            t_resolve_inactive, t_list_empty]
