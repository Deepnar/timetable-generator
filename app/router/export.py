from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import get_db
from app.models.generation import TimetableInstance
from app.models.admin import Admin
from app.utils.auth import get_current_admin
from app.services.export_service import generate_timetable_pdf, generate_faculty_pdf
import csv
import io

router = APIRouter(prefix="/export", tags=["Export"])


@router.get("/instances/{instance_id}/pdf")
def export_timetable_pdf(
    instance_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    instance = db.scalars(
        select(TimetableInstance).where(
            TimetableInstance.id == instance_id)
    ).first()
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )

    buffer = generate_timetable_pdf(
        instance_id=instance_id,
        db=db,
        title=f"Timetable — {instance.label or f'Instance {instance_id}'}"
    )

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=timetable_instance_{instance_id}.pdf"
        }
    )


@router.get("/instances/{instance_id}/faculty/{faculty_id}/pdf")
def export_faculty_pdf(
    instance_id: int,
    faculty_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    buffer = generate_faculty_pdf(
        faculty_id=faculty_id,
        instance_id=instance_id,
        db=db
    )
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=faculty_{faculty_id}_timetable.pdf"
        }
    )


@router.get("/instances/{instance_id}/csv")
def export_timetable_csv(
    instance_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    from app.models.generation import TimetableSlot
    from app.models.rooms import Room
    from app.models.faculty import Faculty
    from app.models.groups import StudentGroup
    from app.models.subjects import Subject
    from app.services.export_service import _get_lookup_maps, DAYS

    slots = db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.instance_id == instance_id
        ).order_by(
            TimetableSlot.day_of_week,
            TimetableSlot.slot_number
        )
    ).all()

    if not slots:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No slots found for this instance"
        )

    maps = _get_lookup_maps(db, slots)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Day", "Slot Number", "Start Time", "End Time",
        "Subject", "Subject Code", "Faculty", "Room",
        "Group", "Session Type", "Manual Override"
    ])

    for slot in slots:
        subject = maps["subjects"].get(slot.subject_id)
        faculty = maps["faculty"].get(slot.faculty_id)
        room = maps["rooms"].get(slot.room_id)
        group = maps["groups"].get(slot.student_group_id)

        writer.writerow([
            DAYS.get(slot.day_of_week, slot.day_of_week),
            slot.slot_number,
            slot.start_time.strftime("%H:%M") if slot.start_time else "",
            slot.end_time.strftime("%H:%M") if slot.end_time else "",
            subject.name if subject else "",
            subject.subject_code if subject else "",
            faculty.name if faculty else "",
            room.name if room else "",
            group.name if group else "",
            slot.session_type,
            "Yes" if slot.is_manual_override else "No"
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=timetable_instance_{instance_id}.csv"
        }
    )