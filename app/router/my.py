"""Teacher self-service portal routes (/my/*, DD-022 #1).

A teacher signs in with a JWT whose role claim is ``teacher`` and whose email
matches a ``Faculty`` row. These endpoints resolve that identity and return
only *their* published schedule — no list endpoint, no instance to hunt for:

- ``GET /my/schedule`` — every PUBLISHED slot for the caller's faculty, with
  subject/room/group names resolved, plus which published instances they come
  from. ``faculty`` is None when the account's email matches no Faculty row.
- ``GET /my/today`` — the caller's sessions for the current weekday (the day
  card). Weekday-based for now; the date-resolution layer (DD-022 #2) will
  resolve ``timetable_overrides`` against a real date.
- ``GET /my/export/{pdf,csv,ical}`` — the caller's own filtered export from
  the newest published instance, without needing to know any ids.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.faculty import Faculty
from app.models.generation import (TimetableInstance, TimetableSlot,
                                   InstanceStatus)
from app.utils.auth import get_current_admin, require_roles
from app.schemas.my import (MyFaculty, MySlot, MyScheduleResponse,
                            MyTodayResponse)
from app.services.export_service import (
    get_filtered_slots, generate_timetable_pdf, generate_timetable_csv,
    generate_timetable_ical,
)

router = APIRouter(prefix="/my", tags=["My schedule"])

# Weekday order for the day card (datetime.weekday(): 0=Mon .. 6=Sun).
_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
              "Saturday", "Sunday"]


def _resolve_faculty(db: Session, admin: Admin) -> Faculty | None:
    """The Faculty row whose email matches the caller's account."""
    return db.scalars(
        select(Faculty).where(Faculty.email == admin.email)
    ).first()


def _published_instances(db: Session) -> list[TimetableInstance]:
    return db.scalars(
        select(TimetableInstance).where(
            TimetableInstance.status == InstanceStatus.PUBLISHED)
    ).all()


def _my_slots(db: Session, faculty: Faculty) -> list[tuple]:
    """The faculty's published slots with names resolved.

    Returns list of (MySlot, day_of_week) tuples sorted by day then slot.
    """
    published = _published_instances(db)
    if not published:
        return []
    ids = [i.id for i in published]

    from app.models.subjects import Subject
    from app.models.rooms import Room
    from app.models.groups import StudentGroup

    subjects = {s.id: s for s in db.scalars(select(Subject)).all()}
    rooms = {r.id: r for r in db.scalars(select(Room)).all()}
    groups = {g.id: g for g in db.scalars(select(StudentGroup)).all()}

    slots = db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.instance_id.in_(ids),
            TimetableSlot.faculty_id == faculty.id,
        ).order_by(TimetableSlot.day_of_week, TimetableSlot.slot_number)
    ).all()

    out = []
    for s in slots:
        subj = subjects.get(s.subject_id)
        room = rooms.get(s.room_id)
        group = groups.get(s.student_group_id)
        out.append(MySlot(
            id=s.id,
            day_of_week=s.day_of_week,
            slot_number=s.slot_number,
            start_time=s.start_time,
            end_time=s.end_time,
            subject_code=subj.subject_code if subj else None,
            subject_name=subj.name if subj else None,
            room_code=room.room_code if room else None,
            group_name=group.name if group else None,
            session_type=getattr(s.session_type, "value", s.session_type),
            is_manual_override=s.is_manual_override,
        ))
    return out


def _faculty_schema(f: Faculty) -> MyFaculty:
    return MyFaculty(id=f.id, name=f.name, email=f.email, department=f.department)


@router.get("/schedule", response_model=MyScheduleResponse,
            dependencies=[Depends(require_roles("teacher"))])
def my_schedule(db: Session = Depends(get_db),
                current: Admin = Depends(get_current_admin)):
    """The caller's own published schedule."""
    faculty = _resolve_faculty(db, current)
    if faculty is None:
        return MyScheduleResponse(faculty=None, slots=[],
                                  published_instance_ids=[])
    slots = _my_slots(db, faculty)
    ids = [i.id for i in _published_instances(db)]
    return MyScheduleResponse(faculty=_faculty_schema(faculty), slots=slots,
                              published_instance_ids=ids)


@router.get("/today", response_model=MyTodayResponse,
            dependencies=[Depends(require_roles("teacher"))])
def my_today(db: Session = Depends(get_db),
             current: Admin = Depends(get_current_admin)):
    """The caller's sessions for the current weekday (day-card data)."""
    faculty = _resolve_faculty(db, current)
    weekday = datetime.utcnow().weekday()
    if faculty is None:
        return MyTodayResponse(faculty=None, day_of_week=weekday, slots=[])
    all_slots = _my_slots(db, faculty)
    today = [s for s in all_slots if s.day_of_week == weekday]
    return MyTodayResponse(faculty=_faculty_schema(faculty),
                           day_of_week=weekday, slots=today)


@router.get("/export/{ext}")
def my_export(ext: str,
              db: Session = Depends(get_db),
              current: Admin = Depends(get_current_admin)):
    """Export the caller's own schedule from the newest published instance.

    Reuses the admin export pipeline filtered to the caller's faculty, so a
    teacher can pull their iCal/PDF without knowing instance or faculty ids.
    """
    from app.router.export import _require_instance

    if ext not in ("pdf", "csv", "ical"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Unknown export format")
    faculty = _resolve_faculty(db, current)
    if faculty is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No faculty record for this account")

    published = _published_instances(db)
    if not published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No published timetable yet")
    newest = max(published, key=lambda i: i.published_at or datetime.min)
    slots = get_filtered_slots(db, newest.id, faculty_id=faculty.id)
    if not slots:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No slots match your schedule")

    name = faculty.name.replace(" ", "-")
    if ext == "pdf":
        buffer = generate_timetable_pdf(
            newest.id, db, title=f"{faculty.name} — Timetable", slots=slots)
        media, filename = "application/pdf", f"{name}-timetable.pdf"
    elif ext == "csv":
        buffer = generate_timetable_csv(slots, db)
        media, filename = "text/csv", f"{name}-timetable.csv"
    else:
        buffer = generate_timetable_ical(slots, db)
        media, filename = "text/calendar", f"{name}-timetable.ics"
    return StreamingResponse(
        buffer, media_type=media,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
