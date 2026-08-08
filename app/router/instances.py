from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, or_
from app.database import get_db
from app.models.admin import Admin
from app.models.constraints import HardConstraint
from app.models.generation import (TimetableInstance, TimetableSlot,
                                    InstanceStatus, TimetableGeneration)
from app.schemas.generation import InstanceResponse, SlotResponse, SlotOverride
from app.utils.auth import get_current_admin
from app.engine.constraint_checker import ConstraintChecker, SlotCandidate
from app.engine.scheduler import Scheduler
from app.services.settings_service import get_settings
from datetime import datetime

router = APIRouter(prefix="/instances", tags=["Instances"])

@router.get("/{generation_id}", response_model=list[InstanceResponse])
def get_instances(
    generation_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
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
    current_admin: Admin = Depends(get_current_admin)
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

    _revalidate_slot(db, slot, instance_id)

    slot.is_manual_override = True
    slot.override_reason = override.override_reason
    db.commit()
    db.refresh(slot)
    return slot


def _revalidate_slot(db: Session, slot: TimetableSlot, instance_id: int):
    """Re-run the hard-constraint checker on an edited slot.

    Manual overrides were previously saved blind. Re-validating the new
    position against the instance's other slots, the cross-timetable
    reservations, and the profile's registry rules keeps a timetable
    conflict-free after manual edits.
    """
    other_slots = db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.instance_id == instance_id,
            TimetableSlot.id != slot.id,
        )
    ).all()

    instance = db.scalars(
        select(TimetableInstance).where(
            TimetableInstance.id == instance_id)).first()
    generation = db.scalars(
        select(TimetableGeneration).where(
            TimetableGeneration.id == instance.generation_id)).first() \
        if instance else None

    hard_constraints = []
    if generation and generation.profile_id:
        hard_constraints = db.scalars(
            select(HardConstraint).where(
                HardConstraint.is_active == True,
                or_(
                    HardConstraint.profile_id == generation.profile_id,
                    HardConstraint.profile_id.is_(None),
                ),
            )
        ).all()

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
    checker = ConstraintChecker(
        db, other_slots,
        settings=get_settings(db),
        reserved=Scheduler(db)._load_published_conflicts(),
        hard_constraints=hard_constraints,
    )
    violations = checker.check_all(candidate)
    if violations:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Override rejected by constraint checker",
                "violations": [str(v) for v in violations],
            },
        )