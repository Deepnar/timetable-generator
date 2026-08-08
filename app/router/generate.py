from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import get_db
from app.models.admin import Admin
from app.models.generation import TimetableGeneration
from app.schemas.generation import GenerationRequest, GenerationResponse
from app.utils.auth import get_current_admin
from app.engine.scheduler import Scheduler
from app.tasks.generation import enqueue_generation
from app.config import settings
import logging

logger = logging.getLogger("timetable")

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

    scheduler = Scheduler(db=db)
    try:
        if settings.ASYNC_GENERATION:
            return _start_async_generation(scheduler, request, current_admin)
        generation = scheduler.run(
            profile_id=request.profile_id,
            timetable_type=request.timetable_type,
            academic_year=request.academic_year,
            semester=request.semester,
            instances_requested=request.instances_requested,
            algorithm=request.algorithm,
            triggered_by=current_admin.id,
            combination_id=request.combination_id,
            variation=request.variation
        )
        return generation
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


def _start_async_generation(
    scheduler: Scheduler,
    request: GenerationRequest,
    current_admin: Admin,
) -> JSONResponse:
    """Persist the PENDING run row, enqueue it, and return 202 immediately.

    The response body is snapshotted from the row's pre-enqueue state so the
    client always sees ``PENDING`` no matter how quickly the worker finishes.
    If the broker is unreachable, fall back to solving synchronously so a
    misconfigured/enqueue outage degrades to the old blocking behaviour instead
    of dropping the generation request entirely.
    """
    generation = scheduler.create_generation(
        profile_id=request.profile_id,
        timetable_type=request.timetable_type,
        academic_year=request.academic_year,
        semester=request.semester,
        instances_requested=request.instances_requested,
        algorithm=request.algorithm,
        triggered_by=current_admin.id,
        combination_id=request.combination_id,
        variation=request.variation
    )
    payload = GenerationResponse.model_validate(generation).model_dump(mode="json")
    scheduler.db.commit()

    try:
        enqueue_generation(generation.id)
    except Exception:
        logger.exception(
            "Failed to enqueue generation run %s; falling back to "
            "synchronous execution", generation.id,
        )
        scheduler.solve_generation(generation.id)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=payload,
    )

@router.get("/{run_id}/status", response_model=GenerationResponse)
def get_generation_status(
    run_id: int,
    db: Session = Depends(get_db),
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
