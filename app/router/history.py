from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional
from app.database import get_db
from app.utils.auth import require_roles
from app.utils.pagination import Pagination, pagination, paginate
from app.models.history import TimetableHistory, TimetableResetLog, ArchiveReason, ResetType
from app.models.generation import TimetableInstance, TimetableSlot, InstanceStatus
from app.models.profiles import TimetableProfile, ProfileResource, ProfileParameter
from datetime import datetime
import json

router = APIRouter(prefix="/history", tags=["History"],
                 dependencies=[Depends(require_roles("admin", "hod"))])


@router.get("/", )
def get_history(
    response: Response,
    academic_year: Optional[str] = None,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
):
    query = select(TimetableHistory)
    if academic_year:
        query = query.where(TimetableHistory.academic_year == academic_year)
    query = query.order_by(TimetableHistory.archived_at.desc())
    history = paginate(db, query, page, response)
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