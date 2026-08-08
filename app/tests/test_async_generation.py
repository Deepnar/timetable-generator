"""Phase 3 tests: async generation pipeline (Celery worker + PENDING polling).

The test suite has no Redis, so these tests exercise the worker task directly
(in-process, via the SQLite ``SessionLocal`` override) and the router's async
branch through Celery's ``task_always_eager`` mode, which runs the task inline.
"""
from app.tests.test_runner import suite, test, seed_minimal


@suite("Phase 3 — Async generation pipeline")
def _phase3_async(s):
    def _run_row(run_id):
        from app.models.generation import TimetableGeneration
        from app.tests.test_runner import TestingSessionLocal
        db = TestingSessionLocal()
        try:
            return db.get(TimetableGeneration, run_id)
        finally:
            db.close()

    @test("sync POST /generate stamps run_duration_ms and completes")
    def t_sync_duration(client):
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        r = client.post("/generate/", headers=headers, json={
            "profile_id": ids["profile"], "academic_year": "2025-26",
            "semester": 3, "timetable_type": "CLASS",
            "instances_requested": 1, "algorithm": "GREEDY",
        })
        assert r.status_code == 201, r.text
        gen = r.json()
        assert gen["generation_status"] == "COMPLETED", gen
        row = _run_row(gen["id"])
        assert row.run_duration_ms is not None and row.run_duration_ms >= 0, row
        assert row.completed_at is not None

    @test("worker task solves a PENDING run to COMPLETED")
    def t_task_success(client):
        from app.engine.scheduler import Scheduler
        from app.models.generation import (AlgorithmType, TimetableGeneration,
                                           TimetableInstance, TimetableSlot,
                                           GenerationStatus)
        from app.tasks.generation import run_generation
        from app.tests.test_runner import TestingSessionLocal
        ids = seed_minimal()
        db = TestingSessionLocal()
        try:
            gen = Scheduler(db).create_generation(
                profile_id=ids["profile"], timetable_type="CLASS",
                academic_year="2025-26", semester=3,
                instances_requested=1, algorithm=AlgorithmType.GREEDY,
                triggered_by=ids["admin"],
            )
            db.commit()
            run_id = gen.id
        finally:
            db.close()

        run_generation(run_id)

        db = TestingSessionLocal()
        try:
            row = db.get(TimetableGeneration, run_id)
            assert row is not None
            assert row.generation_status == GenerationStatus.COMPLETED, (
                row.error_log or row.generation_status)
            assert row.instances_produced == 1
            assert row.run_duration_ms is not None
            assert row.completed_at is not None
            inst = db.query(TimetableInstance).filter_by(
                generation_id=run_id).first()
            assert inst is not None
            slots = db.query(TimetableSlot).filter_by(
                instance_id=inst.id).count()
            assert slots == 3, slots
        finally:
            db.close()

    @test("worker task marks a broken run FAILED with error_log")
    def t_task_failure(client):
        from app.engine.scheduler import Scheduler
        from app.models.generation import (AlgorithmType, TimetableGeneration,
                                           GenerationStatus)
        from app.models.profiles import TimetableProfile
        from app.tasks.generation import run_generation
        from app.tests.test_runner import TestingSessionLocal
        ids = seed_minimal()
        db = TestingSessionLocal()
        try:
            gen = Scheduler(db).create_generation(
                profile_id=ids["profile"], timetable_type="CLASS",
                academic_year="2025-26", semester=3,
                instances_requested=1, algorithm=AlgorithmType.GREEDY,
                triggered_by=ids["admin"],
            )
            # Break the input contract: the run references a profile that no
            # longer exists, so resolution inside solve_generation must fail.
            profile = db.get(TimetableProfile, ids["profile"])
            db.delete(profile)
            db.commit()
            run_id = gen.id
        finally:
            db.close()

        run_generation(run_id)

        row = _run_row(run_id)
        assert row.generation_status == GenerationStatus.FAILED, row.generation_status
        assert row.error_log, "error_log should record the failure"
        assert row.completed_at is not None
        assert row.run_duration_ms is not None

    @test("async POST /generate returns 202 PENDING and polling sees COMPLETED")
    def t_async_http(client):
        from celery import current_app
        from app.config import settings
        from app.tests.test_runner import login_token, auth_headers
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        current_app.conf.task_always_eager = True
        settings.ASYNC_GENERATION = True
        try:
            r = client.post("/generate/", headers=headers, json={
                "profile_id": ids["profile"], "academic_year": "2025-26",
                "semester": 3, "timetable_type": "CLASS",
                "instances_requested": 1, "algorithm": "GREEDY",
            })
            assert r.status_code == 202, r.text
            body = r.json()
            # The enqueue response is the PENDING snapshot taken at dispatch;
            # it must not reflect whatever the worker does afterwards.
            assert body["generation_status"] == "PENDING", body
            assert body["instances_produced"] == 0, body
            run_id = body["id"]

            # Eager mode completed the run inline, so polling reflects it.
            r2 = client.get(f"/generate/{run_id}/status", headers=headers)
            assert r2.status_code == 200, r2.text
            status = r2.json()
            assert status["generation_status"] == "COMPLETED", status
            assert status["instances_produced"] == 1, status
            assert status["completed_at"] is not None, status
        finally:
            settings.ASYNC_GENERATION = False
            current_app.conf.task_always_eager = False

    @test("async POST /generate rejects a bad profile immediately (404)")
    def t_async_404(client):
        from app.config import settings
        from app.tests.test_runner import login_token, auth_headers
        seed_minimal()
        headers = auth_headers(login_token(client))
        settings.ASYNC_GENERATION = True
        try:
            r = client.post("/generate/", headers=headers, json={
                "profile_id": 999999, "academic_year": "2025-26",
                "semester": 3, "timetable_type": "CLASS",
                "instances_requested": 1, "algorithm": "GREEDY",
            })
            assert r.status_code == 404, r.text
        finally:
            settings.ASYNC_GENERATION = False

    return [t_sync_duration, t_task_success, t_task_failure,
            t_async_http, t_async_404]
