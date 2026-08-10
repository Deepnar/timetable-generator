"""Email Notifications on Publish tests.

The suite has no SMTP server, so every test either (a) enables the mailer and
substitutes a fake delivery layer to capture composed messages, or (b) verifies
the graceful-degradation path (email unconfigured -> publish sends nothing and
never blocks). SMTP settings are mutated on the shared ``app.config.settings``
object and restored in ``finally``.
"""
from unittest import mock

from app.tests.test_runner import suite, test
from app.config import settings
from app.services import mail_service


def _enable_email():
    """Turn the mailer on with a fake SMTP and return the previous state."""
    prev = {
        "enabled": settings.EMAIL_ENABLED,
        "host": settings.SMTP_HOST,
        "port": settings.SMTP_PORT,
        "from": settings.SMTP_FROM,
    }
    settings.EMAIL_ENABLED = True
    settings.SMTP_HOST = "smtp.example.com"
    settings.SMTP_PORT = 587
    settings.SMTP_FROM = "timetable@example.com"
    return prev


def _restore_email(prev):
    settings.EMAIL_ENABLED = prev["enabled"]
    settings.SMTP_HOST = prev["host"]
    settings.SMTP_PORT = prev["port"]
    settings.SMTP_FROM = prev["from"]


def _generate_one(client, headers, profile_id):
    r = client.post("/generate/", headers=headers, json={
        "profile_id": profile_id, "academic_year": "2025-26",
        "semester": 3, "timetable_type": "CLASS",
        "instances_requested": 1, "algorithm": "GREEDY",
    })
    assert r.status_code == 201, r.text
    gen = r.json()
    r = client.get(f"/instances/{gen['id']}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()[0]["id"]


def _set_incharge_email(group_id: int, email: str):
    from app.tests.test_runner import TestingSessionLocal
    from app.models.groups import StudentGroup
    db = TestingSessionLocal()
    try:
        group = db.get(StudentGroup, group_id)
        group.incharge_email = email
        db.commit()
    finally:
        db.close()


def _set_notification_emails(emails: list[str]):
    from app.tests.test_runner import TestingSessionLocal, ensure_settings
    ensure_settings({"config_json": {"notification_emails": emails}})


@suite("Email Notifications on Publish — composition")
def _email_composition(s):
    @test("faculty get a personal PDF, HOD a summary, incharge the group PDF")
    def t_composition(client):
        from app.tests.test_runner import seed_minimal, login_token, auth_headers, TestingSessionLocal
        from app.models.generation import TimetableInstance
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        instance_id = _generate_one(client, headers, ids["profile"])

        _set_incharge_email(ids["group"], "incharge@x.com")
        _set_notification_emails(["hod@x.com"])

        prev = _enable_email()
        try:
            sent = []
            with mock.patch.object(mail_service, "_deliver", side_effect=sent.append):
                db = TestingSessionLocal()
                try:
                    instance = db.get(TimetableInstance, instance_id)
                    messages = mail_service.send_publish_notifications(instance, db)
                finally:
                    db.close()

            assert len(sent) == 3, f"expected 3 messages, got {len(sent)}"
            to = {m["To"] for m in sent}
            assert to == {"alice@x.com", "hod@x.com", "incharge@x.com"}, to

            by_to = {m["To"]: m for m in sent}
            faculty_msg = by_to["alice@x.com"]
            assert "Your timetable" in faculty_msg["Subject"]
            assert "published" in faculty_msg["Subject"].lower()
            hod_msg = by_to["hod@x.com"]
            assert "Timetable published" in hod_msg["Subject"]
            assert "Your timetable" not in hod_msg["Subject"]
            incharge_msg = by_to["incharge@x.com"]
            assert "CS-A" in incharge_msg["Subject"]

            for m in sent:
                pdfs = list(m.iter_attachments())
                assert len(pdfs) == 1, f"{m['To']} must carry exactly one PDF"
                payload = pdfs[0].get_payload(decode=True)
                assert payload.startswith(b"%PDF"), f"{m['To']} attachment is not a PDF"

            assert "Sessions" in faculty_msg.get_body(preferencelist=("plain",)).get_content()
            assert settings.SMTP_FROM in {m["From"] for m in sent}
        finally:
            _restore_email(prev)

    @test("a recipient with no slots is skipped")
    def t_skip_empty(client):
        from app.tests.test_runner import seed_minimal, login_token, auth_headers, TestingSessionLocal
        from app.models.generation import TimetableInstance
        from app.models.faculty import Faculty
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        instance_id = _generate_one(client, headers, ids["profile"])

        _set_notification_emails(["hod@x.com"])

        prev = _enable_email()
        try:
            # Add a faculty with no sessions: they must not be mailed.
            db = TestingSessionLocal()
            try:
                db.add(Faculty(name="Idle", email="idle@x.com", department="CS"))
                db.commit()
                instance = db.get(TimetableInstance, instance_id)
                messages = mail_service.send_publish_notifications(instance, db)
            finally:
                db.close()

            assert all(m["To"] != "idle@x.com" for m in messages)
            assert any(m["To"] == "hod@x.com" for m in messages)
        finally:
            _restore_email(prev)

    @test("a mail delivery failure is logged, never raised")
    def t_failure_swallowed(client):
        from app.tests.test_runner import seed_minimal, login_token, auth_headers, TestingSessionLocal
        from app.models.generation import TimetableInstance
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        instance_id = _generate_one(client, headers, ids["profile"])
        _set_incharge_email(ids["group"], "incharge@x.com")
        _set_notification_emails(["hod@x.com"])

        prev = _enable_email()
        try:
            db = TestingSessionLocal()
            try:
                instance = db.get(TimetableInstance, instance_id)
                with mock.patch.object(
                    mail_service, "_deliver",
                    side_effect=RuntimeError("SMTP gone"),
                ):
                    messages = mail_service.send_publish_notifications(instance, db)
                assert len(messages) == 3, "every message is still attempted"
            finally:
                db.close()
        finally:
            _restore_email(prev)

    return [t_composition, t_skip_empty, t_failure_swallowed]


@suite("Email Notifications on Publish — degradation")
def _email_degradation(s):
    @test("an unconfigured mailer is a no-op and never spawns a thread")
    def t_noop_when_disabled(client):
        assert mail_service.is_email_enabled() is False
        prev = _enable_email()
        try:
            settings.SMTP_HOST = ""
            assert mail_service.is_email_enabled() is False
            with mock.patch("threading.Thread", side_effect=AssertionError("must not thread")):
                mail_service.dispatch_publish_notifications(999)
        finally:
            _restore_email(prev)

    @test("send_publish_notifications returns [] when email is disabled")
    def t_empty_when_disabled(client):
        from app.tests.test_runner import seed_minimal, login_token, auth_headers, TestingSessionLocal
        from app.models.generation import TimetableInstance
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        instance_id = _generate_one(client, headers, ids["profile"])
        _set_incharge_email(ids["group"], "incharge@x.com")
        _set_notification_emails(["hod@x.com"])

        # conftest leaves EMAIL_ENABLED=False / SMTP_HOST="" here.
        assert mail_service.is_email_enabled() is False
        with mock.patch.object(mail_service, "_deliver") as deliver:
            db = TestingSessionLocal()
            try:
                instance = db.get(TimetableInstance, instance_id)
                messages = mail_service.send_publish_notifications(instance, db)
            finally:
                db.close()
        assert messages == []
        deliver.assert_not_called()

    @test("POST /instances/{id}/publish triggers the notifications dispatch")
    def t_publish_triggers(client):
        from app.tests.test_runner import seed_minimal, login_token, auth_headers
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        instance_id = _generate_one(client, headers, ids["profile"])

        calls = []
        with mock.patch.object(
            mail_service, "dispatch_publish_notifications",
            side_effect=lambda iid: calls.append(iid),
        ):
            r = client.post(f"/instances/{instance_id}/publish", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "PUBLISHED"
        assert calls == [instance_id], calls

    @test("publish succeeds even when dispatch raises (best-effort)")
    def t_publish_never_blocked(client):
        from app.tests.test_runner import seed_minimal, login_token, auth_headers
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        instance_id = _generate_one(client, headers, ids["profile"])

        with mock.patch.object(
            mail_service, "dispatch_publish_notifications",
            side_effect=RuntimeError("boom"),
        ):
            r = client.post(f"/instances/{instance_id}/publish", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "PUBLISHED"

    return [t_noop_when_disabled, t_empty_when_disabled, t_publish_triggers,
            t_publish_never_blocked]
