from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import get_db
from app.models.history import TimetableHistory, TimetableResetLog, ArchiveReason, ResetType
from app.models.generation import TimetableInstance, TimetableSlot, InstanceStatus
from app.models.profiles import TimetableProfile, ProfileResource, ProfileParameter
from app.models.admin import Admin
from app.utils.auth import get_current_admin
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json

router = APIRouter(prefix="/reset", tags=["Reset"])


class ResetRequest(BaseModel):
    reset_type: ResetType
    academic_year: str
    profile_ids: Optional[list[int]] = None
    notes: Optional[str] = None


def _archive_instance(
    instance: TimetableInstance,
    academic_year: str,
    semester: int | None,
    reason: ArchiveReason,
    admin_id: int,
    db: Session
):
    """Snapshot a published instance into timetable_history."""
    slots = db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.instance_id == instance.id
        )
    ).all()

    snapshot = {
        "instance_id": instance.id,
        "generation_id": instance.generation_id,
        "label": instance.label,
        "soft_score": instance.soft_score,
        "published_at": str(instance.published_at),
        "slots": [
            {
                "day_of_week": s.day_of_week,
                "slot_number": s.slot_number,
                "start_time": str(s.start_time),
                "end_time": str(s.end_time),
                "subject_id": s.subject_id,
                "faculty_id": s.faculty_id,
                "room_id": s.room_id,
                "student_group_id": s.student_group_id,
                "session_type": s.session_type,
                "is_manual_override": s.is_manual_override,
            }
            for s in slots
        ]
    }

    history = TimetableHistory(
        original_instance_id=instance.id,
        academic_year=academic_year,
        semester=semester,
        snapshot_json=snapshot,
        archived_by=admin_id,
        archived_at=datetime.utcnow(),
        archive_reason=reason
    )
    db.add(history)


@router.post("/")
def trigger_reset(
    request: ResetRequest,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    archived_count = 0
    profiles_cleared = []

    if request.reset_type == ResetType.FULL_YEAR:
        # archive all published instances
        published = db.scalars(
            select(TimetableInstance).where(
                TimetableInstance.status == InstanceStatus.PUBLISHED
            )
        ).all()

        for instance in published:
            _archive_instance(
                instance=instance,
                academic_year=request.academic_year,
                semester=None,
                reason=ArchiveReason.YEAR_RESET,
                admin_id=current_admin.id,
                db=db
            )
            instance.status = InstanceStatus.ARCHIVED
            archived_count += 1

        # clear all profile resources and parameters
        all_profiles = db.scalars(select(TimetableProfile)).all()
        for profile in all_profiles:
            resources = db.scalars(
                select(ProfileResource).where(
                    ProfileResource.profile_id == profile.id
                )
            ).all()
            for r in resources:
                db.delete(r)

            params = db.scalars(
                select(ProfileParameter).where(
                    ProfileParameter.profile_id == profile.id
                )
            ).all()
            for p in params:
                db.delete(p)

            profile.is_archived = True
            profiles_cleared.append(profile.id)

    elif request.reset_type == ResetType.PROFILE_SPECIFIC:
        if not request.profile_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="profile_ids required for PROFILE_SPECIFIC reset"
            )

        for profile_id in request.profile_ids:
            resources = db.scalars(
                select(ProfileResource).where(
                    ProfileResource.profile_id == profile_id
                )
            ).all()
            for r in resources:
                db.delete(r)

            params = db.scalars(
                select(ProfileParameter).where(
                    ProfileParameter.profile_id == profile_id
                )
            ).all()
            for p in params:
                db.delete(p)

            profile = db.scalars(
                select(TimetableProfile).where(
                    TimetableProfile.id == profile_id
                )
            ).first()
            if profile:
                profile.is_archived = True
                profiles_cleared.append(profile_id)

    # log the reset
    reset_log = TimetableResetLog(
        reset_type=request.reset_type,
        academic_year=request.academic_year,
        profiles_reset={"profile_ids": profiles_cleared},
        reset_by=current_admin.id,
        reset_at=datetime.utcnow(),
        notes=request.notes
    )
    db.add(reset_log)
    db.commit()

    return {
        "message": "Reset completed successfully",
        "reset_type": request.reset_type,
        "academic_year": request.academic_year,
        "instances_archived": archived_count,
        "profiles_cleared": profiles_cleared,
        "reset_logged_at": datetime.utcnow()
    }


@router.get("/log")
def get_reset_log(
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    logs = db.scalars(
        select(TimetableResetLog).order_by(
            TimetableResetLog.reset_at.desc()
        )
    ).all()
    return [
        {
            "id": log.id,
            "reset_type": log.reset_type,
            "academic_year": log.academic_year,
            "profiles_reset": log.profiles_reset,
            "reset_at": log.reset_at,
            "notes": log.notes
        }
        for log in logs
    ]