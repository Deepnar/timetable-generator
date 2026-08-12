from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import get_db
from app.models.admin import Admin
from app.models.generation import (TimetableInstance, TimetableSlot,
                                    InstanceStatus, TimetableGeneration)
from app.models.profiles import ResourceType
from app.schemas.generation import (InstanceResponse, SlotResponse,
                                    SlotOverride, SlotOverrideDraft)
from app.utils.auth import get_current_admin, require_roles
from app.utils.pagination import Pagination, pagination, paginate
from app.engine.constraint_checker import ConstraintChecker, SlotCandidate
from app.engine.profile_resolver import ProfileResolver
from app.engine.scheduler import Scheduler
from app.services.settings_service import get_settings
from app.services import notification_service
from datetime import datetime, time
import logging

logger = logging.getLogger("timetable")

router = APIRouter(prefix="/instances", tags=["Instances"],
                 dependencies=[Depends(require_roles("admin", "hod"))])

@router.get("/", response_model=list[InstanceResponse])
def list_instances(
    response: Response,
    generation_id: int | None = None,
    status_filter: str | None = None,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
):
    """List every generated instance (optionally per generation/status), newest first.

    Registered before ``/{generation_id}`` so the literal ``/`` list route is
    not shadowed by the path param route. Paginated with X-Total-Count like
    every other top-level list.
    """
    query = select(TimetableInstance).order_by(
        TimetableInstance.id.desc())
    if generation_id is not None:
        query = query.where(TimetableInstance.generation_id == generation_id)
    if status_filter is not None:
        query = query.where(TimetableInstance.status == status_filter)
    return paginate(db, query, page, response)

@router.get("/{generation_id}", response_model=list[InstanceResponse])
def get_instances(
    generation_id: int,
    db: Session = Depends(get_db),
):
    instances = db.scalars(
        select(TimetableInstance).where(
            TimetableInstance.generation_id == generation_id
        )
    ).all()
    if not instances:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No instances found for generation {generation_id}"
        )
    return instances

@router.get("/{instance_id}/slots", response_model=list[SlotResponse])
def get_slots(
    instance_id: int,
    db: Session = Depends(get_db),
):
    slots = db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.instance_id == instance_id
        ).order_by(
            TimetableSlot.day_of_week,
            TimetableSlot.slot_number
        )
    ).all()
    return slots

@router.post("/{instance_id}/select", response_model=InstanceResponse)
def select_instance(
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
    instance.status = InstanceStatus.SELECTED
    instance.selected_by = current_admin.id
    instance.selected_at = datetime.utcnow()
    db.commit()
    db.refresh(instance)
    return instance

@router.post("/{instance_id}/publish", response_model=InstanceResponse)
def publish_instance(
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
    if instance.status not in [InstanceStatus.SELECTED, InstanceStatus.DRAFT]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only DRAFT or SELECTED instances can be published"
        )

    # archive any previously published instance for same generation
    generation = db.scalars(
        select(TimetableGeneration).where(
            TimetableGeneration.id == instance.generation_id)
    ).first()
    if generation:
        previously_published = db.scalars(
            select(TimetableInstance).where(
                TimetableInstance.generation_id == generation.id,
                TimetableInstance.status == InstanceStatus.PUBLISHED
            )
        ).all()
        for old in previously_published:
            old.status = InstanceStatus.ARCHIVED

    instance.status = InstanceStatus.PUBLISHED
    instance.published_at = datetime.utcnow()
    db.commit()
    db.refresh(instance)

    # Fire the publish notifications after the commit so a mail outage can
    # never roll back a successful publish. In-app rows + emails are
    # dispatched best-effort (DD-027); SMTP being unconfigured is a no-op.
    try:
        notification_service.dispatch_publish(instance.id)
    except Exception:
        logger.exception("Publish notifications failed for instance %s", instance.id)

    return instance

@router.patch("/{instance_id}/slots/{slot_id}",
              response_model=SlotResponse)
def override_slot(
    instance_id: int,
    slot_id: int,
    override: SlotOverride,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    slot = db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.id == slot_id,
            TimetableSlot.instance_id == instance_id
        )
    ).first()
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Slot {slot_id} not found in instance {instance_id}"
        )

    # apply only provided fields
    update_data = override.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key != "override_reason":
            setattr(slot, key, value)

    # A move to a new slot_number must carry the new slot's start/end times so
    # the stored row stays consistent with the profile's time grid even though
    # the client only sent the slot index.
    _, resolved = _generation_profile(db, instance_id)
    if resolved is not None and "slot_number" in update_data:
        grid = _slot_time_grid(resolved)
        slot_times = grid.get(slot.slot_number)
        if slot_times:
            slot.start_time, slot.end_time = slot_times

    candidate = SlotCandidate(
        instance_id=instance_id,
        day_of_week=slot.day_of_week,
        slot_number=slot.slot_number,
        start_time=slot.start_time,
        end_time=slot.end_time,
        faculty_id=slot.faculty_id,
        room_id=slot.room_id,
        student_group_id=slot.student_group_id,
        subject_id=slot.subject_id,
        session_type=slot.session_type,
        slot_date=slot.slot_date,
    )
    violations = _check_candidate(db, candidate, instance_id, slot_id)
    if violations:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Override rejected by constraint checker",
                "violations": [str(v) for v in violations],
            },
        )

    slot.is_manual_override = True
    slot.override_reason = override.override_reason
    db.commit()
    db.refresh(slot)
    return slot


@router.post("/{instance_id}/slots/{slot_id}/revalidate")
def revalidate_slot(
    instance_id: int,
    slot_id: int,
    proposed: SlotOverrideDraft,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Dry-run the constraint checker against a proposed override.

    Returns the violations the change would cause without touching the slot,
    so the frontend can show "no conflicts" before the admin commits. A clean
    result is a 200 with an empty ``violations`` list — unlike the PATCH which
    surfaces conflicts as a 409.
    """
    slot = db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.id == slot_id,
            TimetableSlot.instance_id == instance_id
        )
    ).first()
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Slot {slot_id} not found in instance {instance_id}"
        )

    # Evaluate the proposed state without mutating the stored slot.
    day_of_week = proposed.day_of_week if proposed.day_of_week is not None else slot.day_of_week
    slot_number = proposed.slot_number if proposed.slot_number is not None else slot.slot_number
    start_time = proposed.start_time if proposed.start_time is not None else slot.start_time
    end_time = proposed.end_time if proposed.end_time is not None else slot.end_time

    # Keep times consistent with the profile grid when only the slot index is
    # proposed (the client shouldn't need to know day_start_time/durations).
    _, resolved = _generation_profile(db, instance_id)
    if resolved is not None:
        grid = _slot_time_grid(resolved)
        slot_times = grid.get(slot_number)
        if slot_times:
            start_time, end_time = slot_times

    candidate = SlotCandidate(
        instance_id=instance_id,
        day_of_week=day_of_week,
        slot_number=slot_number,
        start_time=start_time,
        end_time=end_time,
        faculty_id=proposed.faculty_id if proposed.faculty_id is not None else slot.faculty_id,
        room_id=proposed.room_id if proposed.room_id is not None else slot.room_id,
        student_group_id=slot.student_group_id,
        subject_id=slot.subject_id,
        session_type=slot.session_type,
        slot_date=slot.slot_date,
    )
    violations = _check_candidate(db, candidate, instance_id, slot_id)
    return {"slot_id": slot_id, "violations": [str(v) for v in violations]}


def _slot_time_grid(resolved) -> dict[int, tuple[time, time]]:
    """Build ``{slot_number: (start, end)}`` from the profile's time params.

    Mirrors the greedy solver's ``_build_slot_times`` so an override that moves
    a session to a new slot gets the correct start/end times without the
    frontend needing to know the profile's ``day_start_time`` / duration.
    """
    params = resolved.params

    def _parse_start(value) -> tuple[int, int]:
        try:
            hour_str, minute_str = str(value).split(":")
            return int(hour_str), int(minute_str)
        except (ValueError, AttributeError):
            return 9, 0

    def _as_int(key: str, default: int) -> int:
        try:
            return int(params.get(key, default))
        except (TypeError, ValueError):
            return default

    slot_duration = _as_int("slot_duration_minutes", 60)
    slots_per_day = _as_int("slots_per_day", 7)
    lunch_after = _as_int("lunch_break_after_slot", 3)
    lunch_duration = _as_int("lunch_break_duration_minutes", 60)

    current_hour, current_minute = _parse_start(params.get("day_start_time", "09:00"))
    grid: dict[int, tuple[time, time]] = {}
    for i in range(1, slots_per_day + 1):
        start = time(current_hour, current_minute)
        total_minutes = current_hour * 60 + current_minute + slot_duration
        end = time(total_minutes // 60, total_minutes % 60)
        grid[i] = (start, end)
        current_hour = total_minutes // 60
        current_minute = total_minutes % 60
        if i == lunch_after:
            lunch_total = current_hour * 60 + current_minute + lunch_duration
            current_hour = lunch_total // 60
            current_minute = lunch_total % 60
    return grid


def _generation_profile(db: Session, instance_id: int):
    """Load the generation + resolved profile backing an instance.

    Returns ``(generation, resolved_or_None)``; the resolved profile is None
    when the instance has no source profile (shouldn't happen in practice).
    """
    instance = db.scalars(
        select(TimetableInstance).where(
            TimetableInstance.id == instance_id)).first()
    generation = db.scalars(
        select(TimetableGeneration).where(
            TimetableGeneration.id == instance.generation_id)).first() \
        if instance else None
    resolved = None
    if generation and (generation.profile_id or generation.combination_id):
        # require_active off so an override still works if the source profile
        # was archived.
        resolved = ProfileResolver(db).resolve(
            profile_id=generation.profile_id,
            combination_id=generation.combination_id,
            require_active=False,
        )
    return generation, resolved


def _check_candidate(db: Session, candidate: SlotCandidate, instance_id: int,
                     exclude_slot_id: int | None = None) -> list:
    """Run the full hard-constraint checker for a slot candidate.

    Shared by the override PATCH (which 409s on any violation) and the
    revalidate dry-run (which returns them). Checks the candidate against the
    instance's other slots, the cross-timetable reservations, and the
    profile's registry rules.
    """
    other_slots = db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.instance_id == instance_id,
            TimetableSlot.id != exclude_slot_id,
        )
    ).all()

    _, resolved = _generation_profile(db, instance_id)

    hard_constraints = []
    exempt_groups = None
    if resolved is not None:
        hard_constraints = resolved.hard_constraints
        # Mirror the scheduler's exam-mode exemption: an exam generation's own
        # groups have suspended their classes, so their published class slots
        # are reusable for the exam being edited.
        if resolved.params.get("session_type") == "EXAM":
            exempt_groups = set(resolved.resource_ids(ResourceType.STUDENT_GROUP))

    checker = ConstraintChecker(
        db, other_slots,
        settings=get_settings(db),
        reserved=Scheduler(db)._load_published_conflicts(exempt_groups=exempt_groups),
        hard_constraints=hard_constraints,
    )
    return checker.check_all(candidate)