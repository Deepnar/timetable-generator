from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import get_db
from app.models.admin import Admin
from app.models.generation import TimetableGeneration
from app.schemas.generation import GenerationRequest, GenerationResponse
from app.utils.auth import get_current_admin, require_roles
from app.utils.pagination import Pagination, pagination, paginate
from app.engine.scheduler import Scheduler, GenerationLockError
from app.tasks.generation import enqueue_generation
from app.services import redis_client
from app.config import settings
import logging

logger = logging.getLogger("timetable")

router = APIRouter(prefix="/generate", tags=["Generate"],
                 dependencies=[Depends(require_roles("admin", "hod"))])

# Security audit M-1: cap how many generation runs one admin/hod can trigger per
# window so a misbehaving client cannot spin the solver endlessly (Redis-backed;
# a no-op when Redis is unavailable).
_GENERATE_LIMIT = 20
_GENERATE_WINDOW = 60


def _rate_limit_generation(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    allowed = redis_client.check_rate_limit(
        "generate", ip, _GENERATE_LIMIT, _GENERATE_WINDOW)
    if allowed is False:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many generation runs, please wait a moment",
        )

@router.get("/", response_model=list[GenerationResponse])
def list_generations(
    response: Response,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
):
    """List generation runs, newest first, with X-Total-Count pagination.

    Ordered by ``triggered_at`` descending so the frontend dashboard can show
    recent runs without a separate "history of runs" endpoint. Same page/skip
    contract as every other top-level list (§7.10).
    """
    query = select(TimetableGeneration).order_by(
        TimetableGeneration.triggered_at.desc(),
        TimetableGeneration.id.desc(),
    )
    return paginate(db, query, page, response)

@router.post("/", response_model=GenerationResponse,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(_rate_limit_generation)])
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
    except GenerationLockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        # Never leak the raw solver/ORM exception to the client (it can carry
        # internal paths, SQL fragments, or user input). The full error is
        # stored on the run row's error_log; the client gets a generic message.
        logger.exception("Generation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Generation failed; check the run status for details"
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
