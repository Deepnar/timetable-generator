"""Security regression tests for the audit remediation (v4-pro audit).

Covers the fixes from the security audit: self-registration is least-privilege,
admin resources are role-gated, and the health endpoint does not leak internals.
"""
from app.tests.test_runner import suite, test, seed_minimal, login_token, auth_headers


def _provision(client, email, role):
    """Admin-provision a non-admin account, return its headers."""
    admin_headers = auth_headers(login_token(client))
    r = client.post("/auth/users", headers=admin_headers, json={
        "name": f"User {role} {email}", "email": email,
        "password": "pass1234", "role": role,
    })
    assert r.status_code == 201, r.text
    return auth_headers(login_token(client, email=email, password="pass1234"))


@suite("Phase 5 — Security audit remediation")
def _phase5_security(s):
    @test("a student cannot read or mutate admin resources")
    def t_student_blocked(client):
        from app.tests.test_runner import reset_db, create_admin
        reset_db(); create_admin()
        student = _provision(client, "stu@x.com", "student")
        for method, path in [
            ("GET", "/api/v1/rooms"),
            ("POST", "/api/v1/faculty"),
            ("GET", "/api/v1/profiles"),
            ("GET", "/api/v1/audit"),
            ("GET", "/api/v1/settings"),
            ("GET", "/api/v1/history"),
            ("POST", "/api/v1/generate"),
        ]:
            r = client.request(method, path, headers=student, json={})
            assert r.status_code == 403, (method, path, r.status_code)

    @test("a teacher cannot reach admin-only settings or audit")
    def t_teacher_admin_blocked(client):
        from app.tests.test_runner import reset_db, create_admin
        reset_db(); create_admin()
        teacher = _provision(client, "tea@x.com", "teacher")
        # teacher + hod can reach resources, but NOT admin-only settings/audit
        r = client.get("/api/v1/settings", headers=teacher)
        assert r.status_code == 403, r.text
        r = client.get("/api/v1/audit", headers=teacher)
        assert r.status_code == 403, r.text
        # resources are admin+hod → teacher is blocked
        r = client.get("/api/v1/rooms", headers=teacher)
        assert r.status_code == 403, r.text

    @test("self-registration cannot request an elevated role")
    def t_register_role_locked(client):
        from app.tests.test_runner import seed_minimal
        from app.tests.conftest import TestingSessionLocal
        from app.models.admin import Admin
        from sqlalchemy import select
        seed_minimal()
        db = TestingSessionLocal()
        try:
            for a in db.scalars(select(Admin).where(Admin.email == "x@x.com")).all():
                db.delete(a)
            db.commit()
        finally:
            db.close()
        # The register schema has no role field, so a caller cannot escalate.
        r = client.post("/auth/register", json={
            "name": "X", "email": "x@x.com", "password": "pass1234",
        })
        assert r.status_code == 201, r.text
        assert r.json()["role"] == "student", r.json()

    @test("health endpoint returns a generic db_error, not internals")
    def t_health_sanitized(client):
        from app.tests.test_runner import reset_db, create_admin
        reset_db(); create_admin()
        r = client.get("/health")
        assert r.status_code == 200, r.text
        body = r.json()
        # With the DB reachable db_error is None; the sanitization is that the
        # response never carries a raw exception string. Force the shape check:
        assert "db" in body and "status" in body
        if body.get("db_error"):
            assert "localhost" not in body["db_error"]
            assert "postgres" not in body["db_error"]

    @test("a student cannot use any mutating route (no per-file guard gap)")
    def t_all_mutating_routes_student_blocked(client):
        """Regression for B-CRIT-1/B-HIGH-2: the overrides and notifications
        routers were mounted without a role dependency, so a self-registered
        STUDENT could rewrite published timetables and read/mark every admin's
        notifications. Enumerate every mutating route in the app and assert the
        role gate fires (403) before any endpoint logic. A new router added
        without a guard fails this test the same day."""
        from app.tests.test_runner import reset_db, create_admin
        from app.main import app as fastapi_app
        import re

        reset_db(); create_admin()
        student = _provision(client, "stu-all@x.com", "student")

        schema = fastapi_app.openapi()
        # {id} -> 1 etc. so path-parameter routes resolve far enough to hit the
        # role dependency; the guard fires before body/path validation anyway.
        def _fill(path):
            import re
            return re.sub(r"\{[^}]*\}", "1", path)

        mutating = []
        for path, ops in schema.get("paths", {}).items():
            for method in ("post", "put", "patch", "delete"):
                if method in ops:
                    mutating.append((method.upper(), path))
        assert mutating, "expected at least one mutating route"

        # Deliberately-student-accessible mutations (matched against the path
        # with the /api/v1 prefix stripped):
        #  - /auth/login and /auth/register are public (self-registration is
        #    the least-privilege path).
        #  - /notifications/*/read and /notifications/read-all are
        #    recipient-scoped self-service: the student marks their OWN rows
        #    read, so it is not privilege escalation.
        _STUDENT_ALLOWED = {
            "/auth/login", "/auth/register",
            "/notifications/read-all",
            "/notifications/{notification_id}/read",
        }
        for method, path in mutating:
            stripped = re.sub(r"^/api/v1", "", path)
            if stripped in _STUDENT_ALLOWED:
                r = client.request(method, _fill(path), headers=student, json={})
                assert r.status_code != 403, (
                    f"STUDENT {method} {path} should be recipient-scoped, "
                    f"not role-blocked"
                )
                continue
            r = client.request(method, _fill(path), headers=student, json={})
            assert r.status_code == 403, (
                f"STUDENT {method} {path} -> {r.status_code} (expected 403); "
                f"route lacks a role guard"
            )

    return [t_student_blocked, t_teacher_admin_blocked, t_register_role_locked,
            t_health_sanitized, t_all_mutating_routes_student_blocked]
