"""Two-channel notifications: in-app dashboard rows + best-effort email.

When a timetable is published or a mid-year change is applied, the relevant
people are notified twice:

* **In-app** — one ``AppNotification`` row per recipient Admin, so the event
  shows up on their dashboard bell. Never depends on SMTP.
* **Email** — the existing publish mailer (``mail_service``) plus a compact
  change-email for mid-year edits. Best-effort; a mail outage is logged, never
  raised.

Recipients are resolved by email from the schema links:
* the instance's faculty (``Faculty.email``) and their Admin accounts,
* the instance's groups' ``incharge_email`` / ``student_email`` (when an Admin
  exists with that email),
* every ``admin``/``hod`` Admin account (the "all relevant people" tier).
"""
from __future__ import annotations

import logging
import threading
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.admin import Admin, AdminRole
from app.models.faculty import Faculty
from app.models.groups import StudentGroup
from app.models.generation import TimetableGeneration, TimetableInstance, TimetableSlot
from app.models.notifications import AppNotification, NotificationKind
from app.models.overrides import TimetableOverride, OverrideType
from app.services import mail_service

logger = logging.getLogger("timetable")


# ── recipient resolution ──────────────────────────────────

def _admin_by_email(db: Session, email: str | None) -> Admin | None:
    if not email:
        return None
    return db.scalars(
        select(Admin).where(Admin.email == email)
    ).first()


def _relevant_admin_ids(db: Session, instance_id: int) -> set[int]:
    """Every Admin who should see events about ``instance_id``:
    admin/hod accounts, the faculty involved, and linked group contacts.
    """
    slots = db.scalars(
        select(TimetableSlot).where(TimetableSlot.instance_id == instance_id)
    ).all()
    ids: set[int] = set()

    # College-level tier: all admin + hod accounts.
    for a in db.scalars(select(Admin).where(
            Admin.role.in_([AdminRole.ADMIN, AdminRole.HOD]))).all():
        ids.add(a.id)

    # Faculty in the instance → their Admin account (email match).
    faculty_ids = {s.faculty_id for s in slots if s.faculty_id is not None}
    if faculty_ids:
        for f in db.scalars(select(Faculty).where(Faculty.id.in_(faculty_ids))).all():
            admin = _admin_by_email(db, f.email)
            if admin:
                ids.add(admin.id)

    # Groups in the instance → incharge / student Admin accounts (email match).
    group_ids = {s.student_group_id for s in slots if s.student_group_id is not None}
    if group_ids:
        for g in db.scalars(
                select(StudentGroup).where(StudentGroup.id.in_(group_ids))).all():
            for email in (g.incharge_email, g.student_email):
                admin = _admin_by_email(db, email)
                if admin:
                    ids.add(admin.id)
    return ids


def _change_faculty_emails(db: Session, override: TimetableOverride) -> set[str]:
    """The faculty emails touched by a change: the slot's teacher and, for a
    cover, the covering teacher too."""
    emails: set[str] = set()
    slot = db.get(TimetableSlot, override.slot_id) if override.slot_id else None
    if slot and slot.faculty_id:
        fac = db.get(Faculty, slot.faculty_id)
        if fac:
            emails.add(fac.email)
    if override.override_type == OverrideType.TEACHER_COVER and override.new_faculty_id:
        fac = db.get(Faculty, override.new_faculty_id)
        if fac:
            emails.add(fac.email)
    return emails


# ── in-app rows ───────────────────────────────────────────

def _notify_admins(db: Session, admin_ids: Iterable[int], kind: NotificationKind,
                   title: str, body: str | None, instance_id: int | None,
                   override_id: int | None) -> int:
    count = 0
    for aid in set(admin_ids):
        db.add(AppNotification(
            recipient_admin_id=aid, kind=kind, title=title, body=body,
            instance_id=instance_id, override_id=override_id,
        ))
        count += 1
    return count


def _publish_title_label(db: Session, instance: TimetableInstance) -> str:
    generation = db.get(TimetableGeneration, instance.generation_id)
    return f"Instance {instance.id} ({generation.academic_year or ''} Sem {generation.semester or ''})".replace(" ()", "").replace("  ", " ").strip()


# ── dispatch (called from routers) ────────────────────────

def dispatch_publish(instance_id: int) -> None:
    """Fan out in-app rows for a publish; the email side is the existing
    ``mail_service`` (no-op when SMTP is unconfigured)."""
    db = SessionLocal()
    try:
        instance = db.get(TimetableInstance, instance_id)
        if instance is None:
            return
        recipients = _relevant_admin_ids(db, instance_id)
        if recipients:
            label = _publish_title_label(db, instance)
            _notify_admins(
                db, recipients, NotificationKind.PUBLISH,
                title="Timetable published",
                body=f"A new timetable ({label}) has been published.",
                instance_id=instance_id, override_id=None,
            )
            db.commit()
        # Fire the existing email side (graceful no-op when disabled).
        mail_service.dispatch_publish_notifications(instance_id)
    except Exception:
        db.rollback()
        logger.exception("Failed to dispatch publish notifications for %s", instance_id)
    finally:
        db.close()


def dispatch_change(override_id: int) -> None:
    """Fan out in-app rows + a compact change email for a mid-year edit."""
    db = SessionLocal()
    try:
        override = db.get(TimetableOverride, override_id)
        if override is None:
            return
        recipients = _relevant_admin_ids(db, override.instance_id)
        # Also include any Admin matching the changed faculty emails (they are
        # not necessarily in the instance's recipient set).
        for email in _change_faculty_emails(db, override):
            admin = _admin_by_email(db, email)
            if admin:
                recipients.add(admin.id)

        title = _change_title(override)
        body = _change_body(db, override)
        if recipients:
            _notify_admins(db, recipients, NotificationKind.CHANGE,
                           title=title, body=body,
                           instance_id=override.instance_id,
                           override_id=override.id)
            db.commit()
        _email_change(override)
    except Exception:
        db.rollback()
        logger.exception("Failed to dispatch change notifications for %s", override_id)
    finally:
        db.close()


def _change_title(override: TimetableOverride) -> str:
    labels = {
        OverrideType.TEACHER_COVER: "Teacher cover applied",
        OverrideType.ROOM_CHANGE: "Room change applied",
        OverrideType.SWAP: "Lecture swap applied",
        OverrideType.TEMP: "Temporary change applied",
        OverrideType.CUSTOM: "Timetable change applied",
    }
    return labels.get(override.override_type, "Timetable change applied")


def _change_body(db: Session, override: TimetableOverride) -> str:
    lines = []
    slot = db.get(TimetableSlot, override.slot_id) if override.slot_id else None
    if slot:
        lines.append(f"day {slot.day_of_week} slot {slot.slot_number}")
    if override.new_faculty_id:
        fac = db.get(Faculty, override.new_faculty_id)
        if fac:
            lines.append(f"teacher → {fac.name}")
    if override.new_room_id:
        from app.models.rooms import Room
        room = db.get(Room, override.new_room_id)
        if room:
            lines.append(f"room → {room.room_code}")
    if override.reason:
        lines.append(f"reason: {override.reason}")
    return "; ".join(lines) if lines else None


def _email_change(override: TimetableOverride) -> None:
    """Best-effort email about a mid-year change to affected faculty.

    Runs in a daemon thread so SMTP latency never blocks the change response.
    """
    if not mail_service.is_email_enabled():
        return
    try:
        threading.Thread(
            target=_run_change_email, args=(override.id,),
            daemon=True, name="change-notification",
        ).start()
    except Exception:
        logger.exception("Failed to start change-notification thread")


def _run_change_email(override_id: int) -> None:
    db = SessionLocal()
    try:
        override = db.get(TimetableOverride, override_id)
        if override is None:
            return
        from email.message import EmailMessage
        from app.config import settings
        from app.models.rooms import Room
        title = _change_title(override)
        body = _change_body(db, override) or "A mid-year timetable change was applied."
        slot = db.get(TimetableSlot, override.slot_id) if override.slot_id else None
        instance = db.get(TimetableInstance, override.instance_id)
        label = f"Instance {instance.id}" if instance else "timetable"
        for email in _change_faculty_emails(db, override):
            msg = EmailMessage()
            msg["Subject"] = f"{title} — {label}"
            msg["From"] = settings.SMTP_FROM
            msg["To"] = email
            msg.set_content(f"{title}\n\n{body}")
            try:
                mail_service._deliver(msg)
            except Exception:
                logger.exception("Failed to send change notification to %s", email)
    finally:
        db.close()
