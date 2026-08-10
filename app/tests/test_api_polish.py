"""API polish: pagination completeness, the global JSON error envelope, and
the /api/v1 versioned prefix.

Covers the gaps from the Phase 5 checklist: every top-level list endpoint
paginates with ``X-Total-Count``, every error returns the ``{"detail": ...}``
envelope (with ``request_id`` on 422/500), and the versioned ``/api/v1``
prefix serves the same routers behind the same auth gate.
"""
from app.tests.test_runner import suite, test, seed_minimal


def _fresh(client):
    from app.tests.test_runner import (
        reset_db, create_admin, login_token, auth_headers,
    )
    reset_db(); create_admin()
    return auth_headers(login_token(client))


def _login(client):
    from app.tests.test_runner import login_token, auth_headers
    return auth_headers(login_token(client))


@suite("Phase 5 — API polish (pagination completeness)")
def _pagination_suite(s):
    def _assert_page(client, headers, url, total=3, limit=2):
        r = client.get(f"{url}&limit={limit}", headers=headers)
        assert r.status_code == 200, r.text
        assert len(r.json()) == limit, r.text
        assert r.headers.get("x-total-count") == str(total), dict(r.headers)
        r2 = client.get(f"{url}&skip={limit}&limit={limit}", headers=headers)
        assert len(r2.json()) == total - limit, r2.text

    @test("profiles list paginates with X-Total-Count")
    def t_profiles(client):
        headers = _fresh(client)
        for i in range(3):
            r = client.post("/profiles/", headers=headers, json={
                "name": f"P{i}", "scope_type": "DEPARTMENT",
                "academic_year": "2025-26", "department": "CS",
            })
            assert r.status_code == 201, r.text
        _assert_page(client, headers, "/profiles/?")

    @test("hard constraints list paginates with X-Total-Count")
    def t_hard(client):
        headers = _fresh(client)
        for _ in range(3):
            r = client.post("/constraints/hard", headers=headers, json={
                "constraint_type": "NO_TEACHER_DOUBLE_BOOK",
            })
            assert r.status_code == 201, r.text
        _assert_page(client, headers, "/constraints/hard?")

    @test("soft constraints list paginates with X-Total-Count")
    def t_soft(client):
        headers = _fresh(client)
        for _ in range(3):
            r = client.post("/constraints/soft", headers=headers, json={
                "constraint_type": "TEACHER_PREFERS_MORNING", "weight": 1.0,
            })
            assert r.status_code == 201, r.text
        _assert_page(client, headers, "/constraints/soft?")

    @test("history list paginates with X-Total-Count")
    def t_history(client):
        seed_minimal()
        from app.tests.conftest import TestingSessionLocal
        from app.models.history import TimetableHistory, ArchiveReason
        from app.models.admin import Admin
        db = TestingSessionLocal()
        try:
            admin = db.query(Admin).first()
            for i in range(3):
                db.add(TimetableHistory(
                    original_instance_id=100 + i,
                    academic_year="2025-26", semester=3,
                    snapshot_json={"n": i},
                    archived_by=admin.id,
                    archive_reason=ArchiveReason.MANUAL,
                ))
            db.commit()
        finally:
            db.close()
        headers = _login(client)
        _assert_page(client, headers, "/history/?")

    @test("room blackouts list paginates with X-Total-Count")
    def t_blackouts(client):
        ids = seed_minimal()
        headers = _login(client)
        for i in range(3):
            r = client.post("/blackouts/", headers=headers, json={
                "room_id": ids["classroom"], "day_of_week": i,
            })
            assert r.status_code == 201, r.text
        _assert_page(client, headers, "/blackouts/?")

    @test("faculty availability list paginates with X-Total-Count")
    def t_availability(client):
        ids = seed_minimal()
        headers = _login(client)
        for i in range(3):
            r = client.post("/faculty_availability/", headers=headers, json={
                "faculty_id": ids["faculty"], "day_of_week": i,
                "availability": "AVAILABLE",
            })
            assert r.status_code == 201, r.text
        _assert_page(client, headers, "/faculty_availability/?")

    @test("generation runs list paginates with X-Total-Count, newest first")
    def t_generations(client):
        seed_minimal()
        from app.tests.conftest import TestingSessionLocal
        from app.models.generation import (
            TimetableGeneration, TimetableType, AlgorithmType, VariationMode,
            GenerationStatus,
        )
        from app.models.admin import Admin
        db = TestingSessionLocal()
        try:
            admin = db.query(Admin).first()
            for i in range(3):
                db.add(TimetableGeneration(
                    profile_id=None, academic_year="2025-26", semester=3,
                    timetable_type=TimetableType.CLASS,
                    generation_status=GenerationStatus.COMPLETED,
                    algorithm_used=AlgorithmType.GREEDY,
                    variation=VariationMode.RANDOM,
                    instances_requested=3, instances_produced=3,
                    triggered_by=admin.id,
                ))
            db.commit()
        finally:
            db.close()
        headers = _login(client)
        _assert_page(client, headers, "/generate/?")
        r = client.get("/generate/?limit=10", headers=headers)
        ids = [row["id"] for row in r.json()]
        assert ids == sorted(ids, reverse=True), r.text

    return [t_profiles, t_hard, t_soft, t_history, t_blackouts, t_availability,
            t_generations]


@suite("Phase 5 — API polish (global error envelope)")
def _error_suite(s):
    @test("an unhandled error returns the consistent envelope")
    def t_unhandled(client):
        from app.main import app
        headers = _fresh(client)

        def _boom():
            raise RuntimeError("boom")

        app.add_api_route("/__test_unhandled__", _boom, methods=["GET"])
        try:
            r = client.get("/__test_unhandled__", headers=headers)
            assert r.status_code == 500
            body = r.json()
            assert body["detail"] == "Internal server error"
            assert body["request_id"], body
            assert set(body) == {"detail", "request_id"}, body
        finally:
            app.router.routes[:] = [
                rt for rt in app.router.routes
                if getattr(rt, "path", None) != "/__test_unhandled__"
            ]

    @test("validation errors carry detail and request_id")
    def t_validation(client):
        headers = _fresh(client)
        r = client.get("/rooms/not-an-int", headers=headers)
        assert r.status_code == 422
        body = r.json()
        assert isinstance(body["detail"], list) and body["detail"], body
        assert body["request_id"], body
        assert set(body) == {"detail", "request_id"}, body

    @test("HTTPExceptions keep the detail envelope")
    def t_http(client):
        headers = _fresh(client)
        r = client.get("/rooms/999999", headers=headers)
        assert r.status_code == 404
        assert set(r.json()) == {"detail"}, r.json()
        r2 = client.get("/does-not-exist", headers=headers)
        assert r2.status_code == 404
        assert r2.json() == {"detail": "Not Found"}, r2.text
        r3 = client.get("/rooms/", )
        assert r3.status_code == 401
        assert r3.json() == {"detail": "Could not validate credentials"}, r3.text

    return [t_unhandled, t_validation, t_http]


@suite("Phase 5 — API polish (/api/v1 versioning)")
def _versioning_suite(s):
    @test("versioned paths serve the same routers behind auth")
    def t_versioned(client):
        headers = _fresh(client)
        r = client.get("/api/v1/rooms/", headers=headers)
        assert r.status_code == 200, r.text
        assert r.headers.get("x-total-count") == "0", dict(r.headers)
        r2 = client.get("/api/v1/rooms/?limit=0", headers=headers)
        assert r2.status_code == 422, r2.text
        assert r2.headers.get("x-request-id"), dict(r2.headers)

    @test("the versioned prefix is not auth-exempt")
    def t_gated(client):
        _fresh(client)
        r = client.get("/api/v1/rooms/")
        assert r.status_code == 401, r.text

    @test("health stays at the root, not versioned")
    def t_health(client):
        _fresh(client)
        assert client.get("/health").status_code == 200
        r = client.get("/api/v1/health")
        assert r.status_code == 401, r.text

    @test("mutations under /api/v1 still audit the versioned path")
    def t_audit(client):
        headers = _fresh(client)
        r = client.post("/api/v1/rooms/", headers=headers, json={
            "name": "V1", "room_code": "V1C", "room_type": "CLASSROOM",
            "capacity": 40, "building": "A",
        })
        assert r.status_code == 201, r.text
        entries = client.get("/api/v1/audit/", headers=headers).json()
        assert any(
            e["method"] == "POST" and e["path"] == "/api/v1/rooms/"
            and e["status_code"] == 201
            for e in entries
        ), entries

    return [t_versioned, t_gated, t_health, t_audit]
