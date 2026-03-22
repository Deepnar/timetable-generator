from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional
from app.database import get_db
from app.models.history import TimetableHistory, TimetableResetLog, ArchiveReason, ResetType
from app.models.generation import TimetableInstance, TimetableSlot, InstanceStatus
from app.models.profiles import TimetableProfile, ProfileResource, ProfileParameter
from app.models.admin import Admin
from app.utils.auth import get_current_admin
from datetime import datetime
import json

router = APIRouter(prefix="/history", tags=["History"])


@router.get("/", )
def get_history(
    academic_year: Optional[str] = None,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    query = select(TimetableHistory)
    if academic_year:
        query = query.where(TimetableHistory.academic_year == academic_year)
    query = query.order_by(TimetableHistory.archived_at.desc())
    history = db.scalars(query).all()
    return [
        {
            "id": h.id,
            "original_instance_id": h.original_instance_id,
            "academic_year": h.academic_year,
            "semester": h.semester,
            "archive_reason": h.archive_reason,
            "archived_at": h.archived_at,
        }
        for h in history
    ]


@router.get("/{id}")
def get_history_snapshot(
    id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    record = db.scalars(
        select(TimetableHistory).where(TimetableHistory.id == id)
    ).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"History record {id} not found"
        )
    return record.snapshot_json