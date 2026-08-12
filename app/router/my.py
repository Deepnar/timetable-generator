"""Self-service portal routes (/my/*, DD-022 #1).

Both roles resolve their identity by email match:

- A **teacher** signs in with a JWT whose role claim is ``teacher`` and whose
  email matches a ``Faculty`` row → ``/my/schedule`` (their own slots),
  ``/my/today``, ``/my/export``.
- A **student** signs in with role ``student`` and an email matching a
  ``StudentGroup.student_email`` row → ``/my/timetable`` (their group's
  published slots), ``/my/today``, ``/my/export``.

No list endpoint and no instance id to hunt for: the identity IS the filter.
"""
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.faculty import Faculty
from app.models.groups import StudentGroup
from app.models.generation import (TimetableInstance, TimetableSlot,
                                   InstanceStatus)
from app.utils.auth import get_current_admin, require_roles
from app.schemas.my import (MyFaculty, MySlot, MyScheduleResponse,
                            MyTimetableResponse, MyTodayResponse, MyGroup)
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


def _resolve_group(db: Session, admin: Admin) -> StudentGroup | None:
    """The StudentGroup whose student_email matches the caller's account."""
    return db.scalars(
        select(StudentGroup).where(StudentGroup.student_email == admin.email)
    ).first()


def _published_instances(db: Session) -> list[TimetableInstance]:
    return db.scalars(
        select(TimetableInstance).where(
            TimetableInstance.status == InstanceStatus.PUBLISHED)
    ).all()


def _my_slots(db: Session, *, faculty_id: int | None = None,
              group_id: int | None = None,
              on_date: date | None = None) -> list[MySlot]:
    """Published slots for a faculty or a group, with names resolved.

    Exactly one of ``faculty_id`` / ``group_id`` should be set. When ``on_date``
    is given the slots are filtered to that weekday AND mid-year changes are
    resolved (DD-022 #2): a permanent cover/room change applies, a TEMP window
    wins inside its dates, a SWAP exchanges faculty/room, and a covered slot
    reports the new teacher/room. Without ``on_date`` the weekly base template
    is returned unchanged.
    """
    published = _published_instances(db)
    if not published:
        return []
    ids = [i.id for i in published]

    from app.models.subjects import Subject
    from app.models.rooms import Room
    from app.models.groups import StudentGroup
    from app.models.faculty import Faculty as FacultyModel
    from app.services.override_resolver import resolve_slots_for_date

    subjects = {s.id: s for s in db.scalars(select(Subject)).all()}
    rooms = {r.id: r for r in db.scalars(select(Room)).all()}
    groups = {g.id: g for g in db.scalars(select(StudentGroup)).all()}
    faculty_rows = {f.id: f for f in db.scalars(select(FacultyModel)).all()}

    query = select(TimetableSlot).where(
        TimetableSlot.instance_id.in_(ids))
    if faculty_id is not None:
        query = query.where(TimetableSlot.faculty_id == faculty_id)
    if group_id is not None:
        query = query.where(TimetableSlot.student_group_id == group_id)
    if on_date is not None:
        query = query.where(TimetableSlot.day_of_week == on_date.weekday())
    query = query.order_by(TimetableSlot.day_of_week, TimetableSlot.slot_number)
    slots = db.scalars(query).all()

    resolved = resolve_slots_for_date(db, slots, on_date) if on_date is not None else {}

    out = []
    for s in slots:
        subj = subjects.get(s.subject_id)
        group = groups.get(s.student_group_id)
        if on_date is not None:
            eff_fac_id, eff_room_id = resolved.get(s.id, (s.faculty_id, s.room_id))
            room = rooms.get(eff_room_id)
            fac = faculty_rows.get(eff_fac_id)
        else:
            room = rooms.get(s.room_id)
            fac = faculty_rows.get(s.faculty_id)
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
            faculty_name=fac.name if fac else None,
            session_type=getattr(s.session_type, "value", s.session_type),
            is_manual_override=s.is_manual_override,
        ))
    return out


def _faculty_schema(f: Faculty) -> MyFaculty:
    return MyFaculty(id=f.id, name=f.name, email=f.email, department=f.department)


def _group_schema(g: StudentGroup) -> MyGroup:
    return MyGroup(id=g.id, name=g.name, department=g.department,
                   year=g.year, semester=g.semester)


@router.get("/schedule", response_model=MyScheduleResponse,
            dependencies=[Depends(require_roles("teacher"))])
def my_schedule(db: Session = Depends(get_db),
                current: Admin = Depends(get_current_admin),
                date: date | None = None):
    """The caller's own published schedule.

    ``?date=YYYY-MM-DD`` returns only that date's sessions with mid-year
    changes resolved (answer "is there class on that day?"). Without it, the
    weekly base template is returned.
    """
    faculty = _resolve_faculty(db, current)
    if faculty is None:
        return MyScheduleResponse(faculty=None, slots=[],
                                  published_instance_ids=[])
    slots = _my_slots(db, faculty_id=faculty.id, on_date=date)
    ids = [i.id for i in _published_instances(db)]
    return MyScheduleResponse(faculty=_faculty_schema(faculty), slots=slots,
                              published_instance_ids=ids)


@router.get("/timetable", response_model=MyTimetableResponse,
            dependencies=[Depends(require_roles("student"))])
def my_timetable(db: Session = Depends(get_db),
                 current: Admin = Depends(get_current_admin),
                 date: date | None = None):
    """The caller's group published timetable (student portal).

    ``?date=YYYY-MM-DD`` returns only that date's sessions with mid-year
    changes resolved.
    """
    group = _resolve_group(db, current)
    if group is None:
        return MyTimetableResponse(group=None, slots=[],
                                   published_instance_ids=[])
    slots = _my_slots(db, group_id=group.id, on_date=date)
    ids = [i.id for i in _published_instances(db)]
    return MyTimetableResponse(group=_group_schema(group), slots=slots,
                               published_instance_ids=ids)


@router.get("/today", response_model=MyTodayResponse,
            dependencies=[Depends(require_roles("teacher", "student"))])
def my_today(db: Session = Depends(get_db),
             current: Admin = Depends(get_current_admin)):
    """The caller's sessions for the current weekday (day-card data).

    Works for both a teacher (their own faculty slots) and a student (their
    group's slots). Mid-year changes are resolved against today's date
    (DD-022 #2): a permanent cover/room change applies, a TEMP window wins
    inside its dates, a SWAP exchanges faculty/room.
    """
    today = datetime.utcnow().date()
    weekday = today.weekday()
    role = getattr(current.role, "value", current.role)
    if role == "student":
        group = _resolve_group(db, current)
        if group is None:
            return MyTodayResponse(faculty=None, group=None,
                                   day_of_week=weekday, slots=[])
        slots = _my_slots(db, group_id=group.id, on_date=today)
        return MyTodayResponse(group=_group_schema(group), faculty=None,
                               day_of_week=weekday, slots=slots)
    faculty = _resolve_faculty(db, current)
    if faculty is None:
        return MyTodayResponse(faculty=None, group=None,
                               day_of_week=weekday, slots=[])
    slots = _my_slots(db, faculty_id=faculty.id, on_date=today)
    return MyTodayResponse(faculty=_faculty_schema(faculty), group=None,
                           day_of_week=weekday, slots=slots)


@router.get("/export/{ext}")
def my_export(ext: str,
              db: Session = Depends(get_db),
              current: Admin = Depends(get_current_admin)):
    """Export the caller's own schedule from the newest published instance.

    Reuses the admin export pipeline filtered to the caller's identity, so a
    teacher pulls their iCal/PDF and a student pulls their group's, without
    knowing instance or faculty/group ids.
    """
    from app.router.export import _require_instance

    if ext not in ("pdf", "csv", "ical"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Unknown export format")

    role = getattr(current.role, "value", current.role)
    if role == "student":
        group = _resolve_group(db, current)
        if group is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="No student group for this account")
        faculty_id, group_id = None, group.id
        name = group.name.replace(" ", "-")
        title = f"{group.name} — Timetable"
    else:
        faculty = _resolve_faculty(db, current)
        if faculty is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="No faculty record for this account")
        faculty_id, group_id = faculty.id, None
        name = faculty.name.replace(" ", "-")
        title = f"{faculty.name} — Timetable"

    published = _published_instances(db)
    if not published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No published timetable yet")
    newest = max(published, key=lambda i: i.published_at or datetime.min)
    slots = get_filtered_slots(db, newest.id, faculty_id=faculty_id,
                               group_id=group_id)
    if not slots:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No slots match your schedule")

    if ext == "pdf":
        buffer = generate_timetable_pdf(newest.id, db, title=title, slots=slots)
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
