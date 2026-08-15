"""Routes for the mid-year change loop (timetable_overrides).

Published timetables are immutable by the normal workflow (re-generate and
re-publish), but real colleges need in-term edits: a teacher leaves, a room is
unavailable, two lectures must swap, or a class runs on a temporary window.
Each change is recorded as a ``TimetableOverride`` row against the published
instance rather than mutating its slots, so the base timetable stays
authoritative and every change is auditable and reversible.

Changes are validated against the instance's *other* slots, the other active
overrides, and the cross-timetable published reservations, so a cover can
never double-book the teacher/room it swaps in.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.generation import (TimetableInstance, TimetableSlot,
                                   InstanceStatus)
from app.models.faculty import Faculty
from app.models.rooms import Room
from app.models.overrides import TimetableOverride, OverrideType
from app.schemas.overrides import (OverrideCreate, OverrideResponse,
                                   OverrideDetail, SwapCreate, AvailableFaculty)
from app.utils.auth import get_current_admin, require_roles
from app.engine.constraint_checker import ConstraintChecker, SlotCandidate
from app.engine.scheduler import Scheduler
from app.services.settings_service import get_settings
from app.services import notification_service

router = APIRouter(
    prefix="/instances", tags=["Mid-year changes"],
    dependencies=[Depends(require_roles("admin", "hod"))])


def _get_instance(db: Session, instance_id: int) -> TimetableInstance:
    instance = db.scalars(
        select(TimetableInstance).where(
            TimetableInstance.id == instance_id)).first()
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Instance {instance_id} not found")
    return instance


def _get_slot(db: Session, instance_id: int, slot_id: int) -> TimetableSlot:
    slot = db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.id == slot_id,
            TimetableSlot.instance_id == instance_id,
        )
    ).first()
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Slot {slot_id} not found in instance {instance_id}")
    return slot


def _other_slots(db: Session, instance_id: int, exclude_slot_ids: set[int]) -> list:
    """Every slot of an instance except the ones being changed."""
    return db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.instance_id == instance_id,
            TimetableSlot.id.not_in(exclude_slot_ids),
        )
    ).all()


def _check_candidate(db: Session, candidate: SlotCandidate, instance_id: int,
                     other_slots: list, exclude_slot_ids: set[int]) -> list:
    """Run the structural checker against the other slots + published
    reservations. The instance being changed is excluded from the published
    reservations so its own base slots don't conflict with the change (only
    OTHER published timetables block a mid-year edit). Data-driven profile
    constraints are intentionally skipped for a mid-year change — the change
    must not break the *published* plan, and the profile may have been edited
    since publication."""
    checker = ConstraintChecker(
        db, other_slots,
        settings=get_settings(db),
        reserved=Scheduler(db)._load_published_conflicts(
            exclude_instance_id=instance_id),
    )
    return checker.check_all(candidate)


def _candidate_for(slot: TimetableSlot, *, faculty_id, room_id,
                   day_of_week=None, slot_number=None) -> SlotCandidate:
    return SlotCandidate(
        instance_id=slot.instance_id,
        day_of_week=day_of_week if day_of_week is not None else slot.day_of_week,
        slot_number=slot_number if slot_number is not None else slot.slot_number,
        start_time=slot.start_time,
        end_time=slot.end_time,
        faculty_id=faculty_id,
        room_id=room_id,
        student_group_id=slot.student_group_id,
        subject_id=slot.subject_id,
        session_type=slot.session_type,
        slot_date=slot.slot_date,
    )


@router.get("/{instance_id}/overrides", response_model=list[OverrideDetail])
def list_overrides(
    instance_id: int,
    resolved: bool | None = None,
    db: Session = Depends(get_db),
):
    """List the mid-year changes recorded against an instance.

    ``?resolved=false`` (default for ``None``) shows only active changes;
    ``?resolved=true`` shows the full history (resolved ones included).
    Each row resolves display names (old/new faculty, old/new room, the
    subject/group, and the day/slot) for the change-list UI.
    """
    _get_instance(db, instance_id)
    query = select(TimetableOverride).where(
        TimetableOverride.instance_id == instance_id)
    if resolved is False:
        query = query.where(TimetableOverride.resolved_at.is_(None))
    elif resolved is True:
        query = query.where(TimetableOverride.resolved_at.isnot(None))
    overrides = db.scalars(
        query.order_by(TimetableOverride.created_at.desc())).all()

    faculty = {f.id: f for f in db.scalars(select(Faculty)).all()}
    rooms = {r.id: r for r in db.scalars(select(Room)).all()}
    slots = db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.instance_id == instance_id)).all()
    slot_by_id = {s.id: s for s in slots}

    out = []
    for o in overrides:
        slot = slot_by_id.get(o.slot_id)
        swap_slot = slot_by_id.get(o.swap_with_slot_id)
        detail = OverrideDetail.model_validate(o)
        if slot is not None:
            detail.slot_day = slot.day_of_week
            detail.slot_number = slot.slot_number
            detail.old_faculty_name = faculty.get(slot.faculty_id).name \
                if slot.faculty_id and slot.faculty_id in faculty else None
            detail.old_room_code = rooms.get(slot.room_id).room_code \
                if slot.room_id and slot.room_id in rooms else None
            detail.new_faculty_name = faculty.get(o.new_faculty_id).name \
                if o.new_faculty_id and o.new_faculty_id in faculty else None
            detail.new_room_code = rooms.get(o.new_room_id).room_code \
                if o.new_room_id and o.new_room_id in rooms else None
        if swap_slot is not None:
            detail.slot_day = swap_slot.day_of_week
            detail.slot_number = swap_slot.slot_number
        out.append(detail)
    return out


@router.post("/{instance_id}/overrides",
             response_model=OverrideResponse,
             status_code=status.HTTP_201_CREATED)
def create_override(
    instance_id: int,
    payload: OverrideCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    """Record a mid-year change and validate it before saving.

    Validates the new state against the instance's other slots, the other
    active overrides, and the published cross-timetable reservations; a
    conflict (e.g. the covering teacher is already booked at that time) is a
    409 and nothing is saved.
    """
    _get_instance(db, instance_id)
    slot = _get_slot(db, instance_id, payload.slot_id)

    if payload.override_type == OverrideType.SWAP:
        if not payload.swap_with_slot_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="SWAP requires swap_with_slot_id")
        swap_slot = _get_slot(db, instance_id, payload.swap_with_slot_id)
        if swap_slot.id == slot.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Cannot swap a slot with itself")
        _validate_swap(db, instance_id, slot, swap_slot)
    else:
        if payload.override_type == OverrideType.TEACHER_COVER:
            if not payload.new_faculty_id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="TEACHER_COVER requires new_faculty_id")
            candidate = _candidate_for(
                slot, faculty_id=payload.new_faculty_id,
                room_id=slot.room_id)
            _validate_candidate(db, instance_id, slot.id, candidate)
        elif payload.override_type == OverrideType.ROOM_CHANGE:
            if not payload.new_room_id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="ROOM_CHANGE requires new_room_id")
            candidate = _candidate_for(
                slot, faculty_id=slot.faculty_id,
                room_id=payload.new_room_id)
            _validate_candidate(db, instance_id, slot.id, candidate)
        elif payload.override_type == OverrideType.TEMP:
            # A temporary window re-uses the cover/room-change validation for
            # its underlying swap; only the date scope differs.
            if payload.date_from and payload.date_to and payload.date_to < payload.date_from:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="date_to must be on/after date_from")
            if payload.new_faculty_id:
                candidate = _candidate_for(
                    slot, faculty_id=payload.new_faculty_id,
                    room_id=slot.room_id)
                _validate_candidate(db, instance_id, slot.id, candidate)
            elif payload.new_room_id:
                candidate = _candidate_for(
                    slot, faculty_id=slot.faculty_id,
                    room_id=payload.new_room_id)
                _validate_candidate(db, instance_id, slot.id, candidate)
            elif not (payload.date_from or payload.date_to):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="TEMP requires new_faculty_id, new_room_id, or a date window")

    override = TimetableOverride(
        instance_id=instance_id,
        slot_id=payload.slot_id,
        override_type=payload.override_type,
        new_faculty_id=payload.new_faculty_id,
        new_room_id=payload.new_room_id,
        swap_with_slot_id=payload.swap_with_slot_id,
        date_from=payload.date_from,
        date_to=payload.date_to,
        reason=payload.reason,
        created_by=current_admin.id,
    )
    db.add(override)
    db.commit()
    db.refresh(override)
    try:
        notification_service.dispatch_change(override.id)
    except Exception:
        pass  # never fail the change because a notification couldn't dispatch
    return override


@router.post("/{instance_id}/slots/{slot_id}/swap",
             response_model=OverrideResponse,
             status_code=status.HTTP_201_CREATED)
def swap_slots(
    instance_id: int,
    slot_id: int,
    payload: SwapCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    """Swap two lectures within an instance (convenience wrapper).

    Equivalent to POST /overrides with override_type=SWAP and
    swap_with_slot_id=payload.with_slot_id.
    """
    _get_instance(db, instance_id)
    slot = _get_slot(db, instance_id, slot_id)
    swap_slot = _get_slot(db, instance_id, payload.with_slot_id)
    if swap_slot.id == slot.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Cannot swap a slot with itself")
    _validate_swap(db, instance_id, slot, swap_slot)

    override = TimetableOverride(
        instance_id=instance_id,
        slot_id=slot.id,
        override_type=OverrideType.SWAP,
        swap_with_slot_id=swap_slot.id,
        reason=payload.reason,
        created_by=current_admin.id,
    )
    db.add(override)
    db.commit()
    db.refresh(override)
    try:
        notification_service.dispatch_change(override.id)
    except Exception:
        pass  # never fail the swap because a notification couldn't dispatch
    return override


@router.delete("/{instance_id}/overrides/{override_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def resolve_override(
    instance_id: int,
    override_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    """Revert a change (mark resolved). The row is kept for the audit trail."""
    _get_instance(db, instance_id)
    override = db.scalars(
        select(TimetableOverride).where(
            TimetableOverride.id == override_id,
            TimetableOverride.instance_id == instance_id,
        )
    ).first()
    if not override:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Override {override_id} not found")
    if override.resolved_at is None:
        from datetime import datetime
        override.resolved_at = datetime.utcnow()
        db.commit()
    return


@router.get("/{instance_id}/overrides/available-faculty",
            response_model=list[AvailableFaculty])
def available_faculty(
    instance_id: int,
    day_of_week: int,
    slot_number: int,
    exclude_slot_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Candidate teachers who are free at the given (day, slot).

    "Free" means not double-booked by the instance's other slots, not by
    other active overrides, and not by a published cross-timetable
    reservation at that time. The calling UI passes the slot being changed as
    ``exclude_slot_id`` so its own teacher is included.
    """
    _get_instance(db, instance_id)

    # Teachers already busy at this (day, slot) in the instance itself.
    busy = set()
    for s in _other_slots(db, instance_id, {exclude_slot_id} if exclude_slot_id else set()):
        if s.faculty_id is not None and s.day_of_week == day_of_week and s.slot_number == slot_number:
            busy.add(s.faculty_id)

    # Teachers busy via other active overrides at this time.
    overrides = db.scalars(
        select(TimetableOverride).where(
            TimetableOverride.instance_id == instance_id,
            TimetableOverride.resolved_at.is_(None),
        )
    ).all()
    override_slots = {o.slot_id for o in overrides}
    slots_in_play = db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.instance_id == instance_id,
            TimetableSlot.id.in_(override_slots),
        )
    ).all() if override_slots else []
    for s in slots_in_play:
        if s.faculty_id is not None and s.day_of_week == day_of_week and s.slot_number == slot_number:
            busy.add(s.faculty_id)

    # Teachers reserved by published cross-timetable bookings at this time
    # (excluding this instance's own base slots — they are the ones being
    # changed, not an external conflict).
    reserved = Scheduler(db)._load_published_conflicts(
        exclude_instance_id=instance_id)
    for (fac_id, d, sn) in reserved.get("faculty", ()):
        if fac_id is not None and d == day_of_week and sn == slot_number:
            busy.add(fac_id)

    query = select(Faculty).where(Faculty.is_active == True)  # noqa: E712
    if busy:
        query = query.where(Faculty.id.not_in(busy))
    free = db.scalars(query).all()
    return [
        AvailableFaculty(id=f.id, name=f.name, email=f.email, department=f.department)
        for f in free
    ]


def _validate_candidate(db: Session, instance_id: int, slot_id: int,
                        candidate: SlotCandidate) -> None:
    """Raise 409 if the candidate state conflicts with the instance's other
    slots or the published reservations."""
    other = _other_slots(db, instance_id, {slot_id})
    violations = _check_candidate(db, candidate, instance_id, other, {slot_id})
    if violations:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Change rejected by constraint checker",
                "violations": [str(v) for v in violations],
            },
        )


def _validate_swap(db: Session, instance_id: int, a: TimetableSlot,
                   b: TimetableSlot) -> None:
    """Validate swapping two slots: each must be valid at the other's
    position (subject/group ride along; only faculty/room move)."""
    other = _other_slots(db, instance_id, {a.id, b.id})

    a_at_b = _candidate_for(b, faculty_id=a.faculty_id, room_id=a.room_id)
    b_at_a = _candidate_for(a, faculty_id=b.faculty_id, room_id=b.room_id)
    va = _check_candidate(db, a_at_b, instance_id, other, {a.id, b.id})
    vb = _check_candidate(db, b_at_a, instance_id, other, {a.id, b.id})
    if va or vb:
        violations = [str(v) for v in va] + [str(v) for v in vb]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Swap rejected by constraint checker",
                "violations": violations,
            },
        )
