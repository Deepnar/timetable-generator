from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import get_db
from app.models.admin import Admin
from app.models.generation import TimetableGeneration, GenerationStatus
from app.schemas.generation import GenerationRequest, GenerationResponse
from app.utils.auth import get_current_admin
from app.engine.scheduler import Scheduler
import time

router = APIRouter(prefix="/generate", tags=["Generate"])

@router.post("/", response_model=GenerationResponse,
             status_code=status.HTTP_201_CREATED)
def trigger_generation(
    request: GenerationRequest,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    if not request.profile_id and not request.combination_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either profile_id or combination_id must be provided"
        )

    start = time.time()
    scheduler = Scheduler(db=db)

    try:
        generation = scheduler.run(
            profile_id=request.profile_id,
            timetable_type=request.timetable_type,
            academic_year=request.academic_year,
            semester=request.semester,
            instances_requested=request.instances_requested,
            algorithm=request.algorithm,
            triggered_by=current_admin.id,
            combination_id=request.combination_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation failed: {str(e)}"
        )

    elapsed = int((time.time() - start) * 1000)
    generation.run_duration_ms = elapsed
    db.commit()

    return generation

@router.get("/{run_id}/status", response_model=GenerationResponse)
def get_generation_status(
    run_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    generation = db.scalars(
        select(TimetableGeneration).where(
            TimetableGeneration.id == run_id)
    ).first()
    if not generation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Generation run {run_id} not found"
        )
    return generation