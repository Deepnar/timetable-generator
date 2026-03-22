from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import get_db
from app.models.admin import Admin
from app.models.generation import (TimetableInstance, TimetableSlot,
                                    InstanceStatus, TimetableGeneration)
from app.schemas.generation import InstanceResponse, SlotResponse, SlotOverride
from app.utils.auth import get_current_admin
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

    slot.is_manual_override = True
    slot.override_reason = override.override_reason
    db.commit()
    db.refresh(slot)
    return slot