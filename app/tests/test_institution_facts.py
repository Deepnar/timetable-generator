"""Phase 3b item 5 — institution facts document (D2 / DD-043).

The importer's hardcoded college constants moved into
``CollegeSettings.config_json``: scheme hours, per-year strengths, per-year
batch counts. These tests pin the document mechanics: one-time seeding,
registrar edits winning, and the settings PUT merge that keeps sibling keys
alive.
"""
from app.tests.test_runner import suite, test, reset_db, create_admin, login_token, auth_headers


@suite("Phase 3b — Institution facts document (D2)")
def _phase3b_institution_facts(s):
    @test("missing facts are seeded once and returned")
    def t_seed(client):
        from app.tests.conftest import TestingSessionLocal
        from app.services.settings_service import get_settings
        from scripts.import_tcet import _institution_facts, _INSTITUTION_FACT_SEEDS
        reset_db()
        db = TestingSessionLocal()
        try:
            facts = _institution_facts(db)
            assert set(facts) == set(_INSTITUTION_FACT_SEEDS), facts
            # The document now holds the seeded values.
            doc = get_settings(db).config_json or {}
            for k, v in facts.items():
                assert doc[k] == v, (k, doc.get(k), v)
            # A second call is a pure read: no re-seeding, same values.
            facts2 = _institution_facts(db)
            assert facts2 == facts
        finally:
            db.close()

    @test("registrar-edited facts win over the adapter's seeds")
    def t_edit_wins(client):
        from app.tests.conftest import TestingSessionLocal
        from app.services.settings_service import get_settings, update_settings
        from scripts.import_tcet import _institution_facts
        reset_db()
        db = TestingSessionLocal()
        try:
            _institution_facts(db)  # seed first
            update_settings(db, config_json={
                "scheme_hours": {"LECTURE": 4, "TUTORIAL": 1, "LAB": 2, "ACTIVITY": 2},
                "year_strengths": {"1": 60, "2": 60, "3": 60, "4": 60},
            })
            facts = _institution_facts(db)
            assert facts["scheme_hours"]["LECTURE"] == 4, facts
            assert facts["year_strengths"]["3"] == 60, facts
            # The unedited key survives untouched.
            assert facts["batches_per_year"]["1"] == 3, facts
        finally:
            db.close()

    @test("scheme hours resolve per kind, defaulting to 3")
    def t_scheme(client):
        from scripts.import_tcet import _scheme_hours, _INSTITUTION_FACT_SEEDS
        facts = dict(_INSTITUTION_FACT_SEEDS)
        assert _scheme_hours(facts, "LECTURE") == 3
        assert _scheme_hours(facts, "TUTORIAL") == 1
        assert _scheme_hours(facts, "LAB") == 2
        assert _scheme_hours(facts, "ACTIVITY") == 2
        assert _scheme_hours(facts, "UNKNOWN") == 3
        # A registrar's document is honoured.
        facts["scheme_hours"] = {"LECTURE": 4, "TUTORIAL": 1, "LAB": 2, "ACTIVITY": 2}
        assert _scheme_hours(facts, "LECTURE") == 4

    @test("--codes parses into a normalized department set")
    def t_codes(client):
        from scripts.import_tcet import _parse_codes
        assert _parse_codes("COMP") == {"COMP"}
        assert _parse_codes("COMP,IT") == {"COMP", "IT"}
        assert _parse_codes("comp, it") == {"COMP", "IT"}
        assert _parse_codes("") == set()

    @test("PUT /settings merges config_json instead of replacing it")
    def t_settings_merge(client):
        from app.tests.test_runner import reset_db, create_admin, login_token, auth_headers
        reset_db(); create_admin()
        token = login_token(client)
        headers = auth_headers(token)
        r = client.put("/settings/", headers=headers,
                       json={"config_json": {"scheme_hours": {"LECTURE": 3}}})
        assert r.status_code == 200, r.text
        r = client.put("/settings/", headers=headers,
                       json={"config_json": {"max_cross_dept_per_day": 2}})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["config_json"] == {
            "scheme_hours": {"LECTURE": 3},
            "max_cross_dept_per_day": 2,
        }, body["config_json"]

    return [t_seed, t_edit_wins, t_scheme, t_codes, t_settings_merge]
