"""Email Notifications on Publish tests.

The suite has no SMTP server, so most tests (a) enable the mailer and
substitute a fake delivery layer to capture composed messages, or (b) verify
the graceful-degradation path (email unconfigured -> publish sends nothing and
never blocks). The live-delivery suite goes further and proves the real
transport: it runs the daemon-thread background path against the SQLite pool,
and delivers over a genuine ``smtplib`` dialog to an in-process loopback SMTP
server. SMTP settings are mutated on the shared ``app.config.settings`` object
and restored in ``finally``.
"""
import socket
import socketserver
import threading
import time
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


class _SmtpHandler(socketserver.StreamRequestHandler):
    """Speaks just enough SMTP for smtplib's EHLO/MAIL/RCPT/DATA/QUIT dialog,
    appending each delivered message body to ``self.server.messages``."""

    def handle(self):
        self.wfile.write(b"220 localhost ESMTP\r\n")
        while True:
            line = self.rfile.readline()
            if not line:
                break
            cmd = line.strip().upper()
            if cmd.startswith(b"EHLO"):
                self.wfile.write(b"250-localhost\r\n250 OK\r\n")
            elif cmd.startswith(b"MAIL") or cmd.startswith(b"RCPT"):
                self.wfile.write(b"250 OK\r\n")
            elif cmd.startswith(b"DATA"):
                self.wfile.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                body = b""
                while True:
                    chunk = self.rfile.readline()
                    if chunk == b".\r\n":
                        break
                    body += chunk
                self.server.messages.append(body)
                self.wfile.write(b"250 OK\r\n")
            elif cmd.startswith(b"QUIT"):
                self.wfile.write(b"221 Bye\r\n")
                break
            else:
                self.wfile.write(b"250 OK\r\n")


class _SmtpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _SmtpHandler)
        self.messages = []


@suite("Email Notifications on Publish — live delivery")
def _email_live_delivery(s):
    @test("dispatch runs the real background thread and delivers")
    def t_background_thread(client):
        from app.tests.test_runner import seed_minimal, login_token, auth_headers
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        instance_id = _generate_one(client, headers, ids["profile"])
        _set_incharge_email(ids["group"], "incharge@x.com")
        _set_notification_emails(["hod@x.com"])

        prev = _enable_email()
        try:
            sent = []
            tracked = []

            class _TrackingThread(threading.Thread):
                def start(self):
                    tracked.append(self)
                    super().start()

            # Keep the _deliver patch live until the worker thread finishes,
            # or the background send would hit the real smtplib path.
            with mock.patch("threading.Thread", new=_TrackingThread):
                with mock.patch.object(mail_service, "_deliver",
                                       side_effect=sent.append):
                    mail_service.dispatch_publish_notifications(instance_id)
                    assert len(tracked) == 1, "dispatch must spawn exactly one thread"
                    assert tracked[0].daemon, "the notification thread must be a daemon"
                    tracked[0].join(timeout=10)

            assert not tracked[0].is_alive(), "the notification thread must finish"
            assert {m["To"] for m in sent} == {
                "alice@x.com", "hod@x.com", "incharge@x.com"
            }, sent
        finally:
            _restore_email(prev)

    @test("the real smtplib path delivers over the wire to an in-process server")
    def t_wire_path(client):
        from app.tests.test_runner import seed_minimal, login_token, auth_headers, TestingSessionLocal
        from app.models.generation import TimetableInstance
        ids = seed_minimal()
        headers = auth_headers(login_token(client))
        instance_id = _generate_one(client, headers, ids["profile"])
        _set_incharge_email(ids["group"], "incharge@x.com")
        _set_notification_emails(["hod@x.com"])

        server = _SmtpServer()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        prev = _enable_email()
        settings.SMTP_HOST = "127.0.0.1"
        settings.SMTP_PORT = server.server_address[1]
        try:
            db = TestingSessionLocal()
            try:
                instance = db.get(TimetableInstance, instance_id)
                # No _deliver patch: the real smtplib dialog runs against the
                # loopback server, proving EHLO/MAIL/RCPT/DATA actually work.
                messages = mail_service.send_publish_notifications(instance, db)
            finally:
                db.close()
            assert len(messages) == 3, "all three recipients are attempted"
            assert len(server.messages) == 3, server.messages
            tos = set()
            for body in server.messages:
                assert b"From: timetable@example.com" in body
                assert b"application/pdf" in body, body[:200]
                for line in body.split(b"\r\n"):
                    if line.lower().startswith(b"to:"):
                        tos.add(line.decode())
            assert any("alice@x.com" in t for t in tos)
            assert any("hod@x.com" in t for t in tos)
            assert any("incharge@x.com" in t for t in tos)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            _restore_email(prev)

    return [t_background_thread, t_wire_path]
