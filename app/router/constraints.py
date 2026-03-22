from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional
from ..database import get_db
from ..models.constraints import HardConstraint, SoftConstraint, ConstraintType
from ..models import Admin
from ..schemas.constraints import (HardConstraintCreate, HardConstraintResponse,
                                      SoftConstraintCreate, SoftConstraintResponse)
from ..utils.auth import get_current_admin

router = APIRouter(prefix="/constraints", tags=["Constraints"])

# ── Hard Constraints ──────────────────────────────────────

@router.get("/hard", response_model=list[HardConstraintResponse])
def get_hard_constraints(
    profile_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = select(HardConstraint).where(HardConstraint.is_active == True)
    if profile_id:
        query = query.where(HardConstraint.profile_id == profile_id)
    return db.scalars(query).all()

@router.post("/hard", status_code=status.HTTP_201_CREATED,
             response_model=HardConstraintResponse)
def create_hard_constraint(
    constraint: HardConstraintCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    new_constraint = HardConstraint(**constraint.model_dump())
    db.add(new_constraint)
    db.commit()
    db.refresh(new_constraint)
    return new_constraint

@router.put("/hard/{id}", response_model=HardConstraintResponse)
def update_hard_constraint(
    id: int,
    updated: HardConstraintCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    constraint = db.scalars(
        select(HardConstraint).where(HardConstraint.id == id)
    ).first()
    if not constraint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Constraint {id} not found")
    for key, value in updated.model_dump().items():
        setattr(constraint, key, value)
    db.commit()
    db.refresh(constraint)
    return constraint

@router.delete("/hard/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hard_constraint(
    id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    constraint = db.scalars(
        select(HardConstraint).where(HardConstraint.id == id)
    ).first()
    if not constraint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Constraint {id} not found")
    constraint.is_active = False
    db.commit()
    return

# ── Soft Constraints ──────────────────────────────────────

@router.get("/soft", response_model=list[SoftConstraintResponse])
def get_soft_constraints(
    profile_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = select(SoftConstraint).where(SoftConstraint.is_active == True)
    if profile_id:
        query = query.where(SoftConstraint.profile_id == profile_id)
    return db.scalars(query).all()

@router.post("/soft", status_code=status.HTTP_201_CREATED,
             response_model=SoftConstraintResponse)
def create_soft_constraint(
    constraint: SoftConstraintCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    new_constraint = SoftConstraint(**constraint.model_dump())
    db.add(new_constraint)
    db.commit()
    db.refresh(new_constraint)
    return new_constraint

@router.put("/soft/{id}", response_model=SoftConstraintResponse)
def update_soft_constraint(
    id: int,
    updated: SoftConstraintCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    constraint = db.scalars(
        select(SoftConstraint).where(SoftConstraint.id == id)
    ).first()
    if not constraint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Constraint {id} not found")
    for key, value in updated.model_dump().items():
        setattr(constraint, key, value)
    db.commit()
    db.refresh(constraint)
    return constraint

@router.delete("/soft/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_soft_constraint(
    id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    constraint = db.scalars(
        select(SoftConstraint).where(SoftConstraint.id == id)
    ).first()
    if not constraint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Constraint {id} not found")
    constraint.is_active = False
    db.commit()
    return

# ── List all available constraint types ───────────────────

@router.get("/types")
def get_constraint_types():
    return {
        "hard": [
            "NO_TEACHER_DOUBLE_BOOK",
            "NO_ROOM_DOUBLE_BOOK",
            "NO_GROUP_DOUBLE_BOOK",
            "ROOM_CAPACITY_SUFFICIENT",
            "ROOM_TYPE_MATCH",
            "RESPECT_TEACHER_UNAVAILABILITY",
            "RESPECT_ROOM_BLACKOUT",
            "CONTIGUOUS_LAB_SLOTS",
            "EXAM_DATE_SEPARATION"
        ],
        "soft": [
            "TEACHER_PREFERS_MORNING",
            "AVOID_CONSECUTIVE_SAME_SUBJECT",
            "MINIMIZE_STUDENT_FREE_SLOTS",
            "MINIMIZE_TEACHER_FREE_SLOTS",
            "DISTRIBUTE_SUBJECTS_EVENLY",
            "BALANCE_TEACHER_LOAD"
        ]
    }
