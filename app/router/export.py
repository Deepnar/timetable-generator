"""Timetable export endpoints — PDF, CSV and iCal, with optional filters.

Every export accepts `group_id`, `faculty_id`, `year` and `department` query
params so an admin can pull a division's grid, one teacher's personal schedule,
a whole year, or a department — not just the full instance.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database import get_db
from app.models.generation import TimetableInstance
from app.services.export_service import (
    get_filtered_slots,
    describe_filters,
    generate_timetable_pdf,
    generate_timetable_csv,
    generate_timetable_ical,
)

router = APIRouter(prefix="/export", tags=["Export"])


def _require_instance(instance_id: int, db: Session) -> TimetableInstance:
    instance = db.scalars(
        select(TimetableInstance).where(TimetableInstance.id == instance_id)
    ).first()
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )
    return instance


def _filename(instance_id: int, ext: str, suffix: str) -> str:
    tag = "_" + suffix.replace(", ", "_").replace(" ", "-") if suffix else ""
    return f"timetable_instance_{instance_id}{tag}.{ext}"


@router.get("/instances/{instance_id}/pdf")
def export_timetable_pdf(
    instance_id: int,
    group_id: Optional[int] = None,
    faculty_id: Optional[int] = None,
    year: Optional[int] = None,
    department: Optional[str] = None,
    db: Session = Depends(get_db),
):
    instance = _require_instance(instance_id, db)
    slots = get_filtered_slots(
        db, instance_id, group_id=group_id, faculty_id=faculty_id,
        year=year, department=department,
    )
    suffix = describe_filters(group_id, faculty_id, year, department)
    base = instance.label or f"Instance {instance_id}"
    title = f"Timetable — {base}" + (f" ({suffix})" if suffix else "")
    buffer = generate_timetable_pdf(instance_id, db, title=title, slots=slots)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={_filename(instance_id, 'pdf', suffix)}"
        },
    )


@router.get("/instances/{instance_id}/csv")
def export_timetable_csv(
    instance_id: int,
    group_id: Optional[int] = None,
    faculty_id: Optional[int] = None,
    year: Optional[int] = None,
    department: Optional[str] = None,
    db: Session = Depends(get_db),
):
    _require_instance(instance_id, db)
    slots = get_filtered_slots(
        db, instance_id, group_id=group_id, faculty_id=faculty_id,
        year=year, department=department,
    )
    if not slots:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No slots match the given filters",
        )
    suffix = describe_filters(group_id, faculty_id, year, department)
    buffer = generate_timetable_csv(slots, db)
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={_filename(instance_id, 'csv', suffix)}"
        },
    )


@router.get("/instances/{instance_id}/ical")
def export_timetable_ical(
    instance_id: int,
    group_id: Optional[int] = None,
    faculty_id: Optional[int] = None,
    year: Optional[int] = None,
    department: Optional[str] = None,
    term_start: Optional[date] = None,
    term_end: Optional[date] = None,
    db: Session = Depends(get_db),
):
    instance = _require_instance(instance_id, db)
    slots = get_filtered_slots(
        db, instance_id, group_id=group_id, faculty_id=faculty_id,
        year=year, department=department,
    )
    if not slots:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No slots match the given filters",
        )
    suffix = describe_filters(group_id, faculty_id, year, department)
    cal_name = (instance.label or f"Instance {instance_id}") + (
        f" ({suffix})" if suffix else ""
    )
    buffer = generate_timetable_ical(
        slots, db, term_start=term_start, term_end=term_end, calendar_name=cal_name
    )
    return StreamingResponse(
        buffer,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f"attachment; filename={_filename(instance_id, 'ics', suffix)}"
        },
    )
