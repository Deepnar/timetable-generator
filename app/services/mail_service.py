"""Best-effort email notifications sent when a timetable is published.

SMTP is opt-in via .env (``EMAIL_ENABLED`` + ``SMTP_*``). When unconfigured,
every public function degrades to a no-op so a missing mail server never
blocks or breaks the publish request — the same graceful-degradation posture
as the Redis client. Delivery runs in a daemon thread from the publish
endpoint, and individual send failures are logged, never raised.

Recipients on publish:
  * every faculty with a slot in the instance  -> their personal schedule PDF
  * every configured HOD/admin address        -> the full-instance summary PDF
  * every group's ``incharge_email``          -> that group's schedule PDF
"""
from __future__ import annotations

import logging
import smtplib
import threading
from email.message import EmailMessage
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.faculty import Faculty
from app.models.generation import TimetableGeneration, TimetableInstance, TimetableSlot
from app.models.groups import StudentGroup
from app.services.export_service import generate_timetable_pdf
from app.services.settings_service import get_settings

logger = logging.getLogger("timetable")

_SUMMARY_EMAILS_CONFIG_KEY = "notification_emails"

_SUMMARY_MSG = "The {label} timetable has been published."
_FACULTY_MSG = "Your personal timetable ({label}) has been published."
_INCHARGE_MSG = "The {label} timetable for {group} has been published."


def is_email_enabled() -> bool:
    """True only when SMTP is fully configured and the master switch is on."""
    return bool(
        settings.EMAIL_ENABLED
        and settings.SMTP_HOST
        and settings.SMTP_PORT
        and settings.SMTP_FROM
    )


def dispatch_publish_notifications(instance_id: int) -> None:
    """Trigger the publish emails from the HTTP layer, without blocking it.

    Runs in a daemon thread so SMTP latency (or an outage) never delays the
    publish response. No-op when email is unconfigured; a failure to start the
    thread is logged and swallowed — the publish already succeeded.
    """
    if not is_email_enabled():
        return
    try:
        threading.Thread(
            target=_run_background,
            args=(instance_id,),
            daemon=True,
            name="publish-notifications",
        ).start()
    except Exception:
        logger.exception("Failed to start publish-notification thread")


def _run_background(instance_id: int) -> None:
    """Open a fresh session and send the notifications for ``instance_id``."""
    db = SessionLocal()
    try:
        instance = db.get(TimetableInstance, instance_id)
        if instance is None:
            return
        send_publish_notifications(instance, db)
    finally:
        db.close()


def send_publish_notifications(instance, db: Session) -> list[EmailMessage]:
    """Compose and deliver the publish emails synchronously.

    Returns the messages handed to the delivery layer (empty when email is
    disabled or no recipient has a contact address). Never raises on SMTP
    failure — each delivery is attempted and logged.
    """
    messages = _build_messages(instance, db)
    for msg in messages:
        try:
            _deliver(msg)
        except Exception:  # never let one bad recipient abort the rest
            logger.exception("Failed to send publish notification to %s", msg["To"])
    return messages


def _summary_recipients(db: Session) -> list[str]:
    """HOD/admin addresses that receive the publish summary.

    The schema has no HOD table; the college singleton's free-form
    ``config_json`` is the designated place for a contact list
    (``config_json["notification_emails"]``).
    """
    config = get_settings(db).config_json or {}
    emails = config.get(_SUMMARY_EMAILS_CONFIG_KEY) or []
    return [e for e in emails if isinstance(e, str) and e.strip()]


def _build_messages(instance, db: Session) -> list[EmailMessage]:
    """Compose one message per recipient audience (see module docstring)."""
    if not is_email_enabled():
        return []

    slots = db.scalars(
        select(TimetableSlot).where(TimetableSlot.instance_id == instance.id)
    ).all()
    if not slots:
        return []

    generation = db.get(TimetableGeneration, instance.generation_id)
    label = instance.label or f"Instance {instance.id}"
    messages: list[EmailMessage] = []

    # Faculty -> personal schedule PDF.
    faculty_ids = {s.faculty_id for s in slots if s.faculty_id is not None}
    faculty = db.scalars(
        select(Faculty).where(Faculty.id.in_(faculty_ids))
    ).all()
    for fac in faculty:
        f_slots = [s for s in slots if s.faculty_id == fac.id]
        if not f_slots:
            continue
        pdf = _render_pdf(instance.id, db, f"Timetable — {fac.name}", f_slots)
        body = _body(_FACULTY_MSG.format(label=label), _summary(f_slots, label))
        messages.append(_message(
            f"Your timetable has been published — {label}",
            fac.email, body,
        ))
        _attach_pdf(messages[-1], pdf, "timetable.pdf")

    # HOD / admin -> full-instance summary PDF.
    if _summary_recipients(db):
        pdf = _render_pdf(instance.id, db, f"Timetable — {label}")
        body = _body(_SUMMARY_MSG.format(label=label), _summary(slots, label, generation))
        for addr in _summary_recipients(db):
            messages.append(_message(
                f"Timetable published — {label}",
                addr, body,
            ))
            _attach_pdf(messages[-1], pdf, "timetable.pdf")

    # Class incharge -> that group's schedule PDF.
    group_ids = {s.student_group_id for s in slots if s.student_group_id is not None}
    groups = db.scalars(
        select(StudentGroup).where(StudentGroup.id.in_(group_ids))
    ).all()
    for grp in groups:
        if not grp.incharge_email:
            continue
        g_slots = [s for s in slots if s.student_group_id == grp.id]
        if not g_slots:
            continue
        pdf = _render_pdf(instance.id, db, f"Timetable — {grp.name}", g_slots)
        body = _body(
            _INCHARGE_MSG.format(label=label, group=grp.name),
            _summary(g_slots, label),
        )
        messages.append(_message(
            f"Timetable published — {label} ({grp.name})",
            grp.incharge_email, body,
        ))
        _attach_pdf(messages[-1], pdf, f"timetable_{grp.name}.pdf")

    return messages


def _render_pdf(instance_id: int, db: Session, title: str, slots=None) -> BytesIO:
    return generate_timetable_pdf(instance_id, db, title=title, slots=slots)


def _summary(slots, label: str, generation=None) -> list[tuple[str, str]]:
    """Key/value lines shared by every notification body."""
    days = len({s.day_of_week for s in slots if s.day_of_week is not None})
    faculty_count = len({s.faculty_id for s in slots if s.faculty_id is not None})
    group_count = len({s.student_group_id for s in slots if s.student_group_id is not None})
    rows = [
        ("Timetable", label),
        ("Sessions", str(len(slots))),
        ("Teaching days", str(days)),
        ("Faculty", str(faculty_count)),
        ("Groups", str(group_count)),
    ]
    if generation is not None:
        rows.insert(1, ("Academic year", generation.academic_year or ""))
        rows.insert(2, ("Semester", str(generation.semester or "")))
    return rows


def _body(intro: str, rows: list[tuple[str, str]]) -> tuple[str, str]:
    """Plain-text and HTML versions of the same notification body."""
    text_lines = [intro, ""]
    text_lines += [f"{k}: {v}" for k, v in rows]
    text = "\n".join(text_lines)

    html = (
        "<html><body>"
        f"<p>{intro}</p>"
        "<table border='0' cellpadding='4'>"
        + "".join(
            f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in rows
        )
        + "</table></body></html>"
    )
    return text, html


def _message(subject: str, to: str, body: tuple[str, str]) -> EmailMessage:
    text, html = body
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def _attach_pdf(msg: EmailMessage, buffer: BytesIO, filename: str) -> None:
    msg.add_attachment(
        buffer.getvalue(),
        maintype="application",
        subtype="pdf",
        filename=filename,
    )


def _deliver(msg: EmailMessage) -> bool:
    """Send one message over SMTP. Logs and swallows failures."""
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_PORT == 587:
                server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("Failed to send publish notification to %s", msg["To"])
        return False
