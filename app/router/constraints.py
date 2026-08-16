from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional
from ..database import get_db
from ..utils.pagination import Pagination, pagination, paginate
from ..models.constraints import (
    HardConstraint, SoftConstraint, ConstraintType,
    HARD_CONSTRAINT_TYPES, SOFT_CONSTRAINT_TYPES,
)
from ..models import Admin
from ..schemas.constraints import (HardConstraintCreate, HardConstraintResponse,
                                      SoftConstraintCreate, SoftConstraintResponse)
from ..utils.auth import get_current_admin, require_roles

router = APIRouter(prefix="/constraints", tags=["Constraints"],
                 dependencies=[Depends(require_roles("admin"))])

# ── Hard Constraints ──────────────────────────────────────

@router.get("/hard", response_model=list[HardConstraintResponse])
def get_hard_constraints(
    response: Response,
    profile_id: Optional[int] = None,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db)
):
    query = select(HardConstraint).where(HardConstraint.is_active == True)
    if profile_id:
        query = query.where(HardConstraint.profile_id == profile_id)
    return paginate(db, query, page, response)

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
    response: Response,
    profile_id: Optional[int] = None,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db)
):
    query = select(SoftConstraint).where(SoftConstraint.is_active == True)
    if profile_id:
        query = query.where(SoftConstraint.profile_id == profile_id)
    return paginate(db, query, page, response)

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
    """Catalog every constraint type with its tier and config schema.

    Phase 3b (A10): the catalog drives the constraint editor UI. Each hard
    type carries the tier that decides its affordance — INVARIANT (locked,
    physics), INSTITUTIONAL (college policy, tunable through rows), OPTIONAL
    (per-profile opt-in) — plus a JSON-schema for its ``config_json`` so the
    UI can render a form without a code change. Soft types are always
    PREFERENCE tier (weighted, never block).
    """
    from app.engine.constraint_registry import (
        CONSTRAINT_TIERS, CONFIG_SCHEMAS,
    )

    return {
        "hard": [
            {
                "type": t.value,
                "tier": CONSTRAINT_TIERS.get(t.value, "OPTIONAL"),
                "config_schema": CONFIG_SCHEMAS.get(t.value, {"type": "object"}),
            }
            for t in HARD_CONSTRAINT_TYPES
        ],
        "soft": [
            {
                "type": t.value,
                "tier": "PREFERENCE",
                "config_schema": {"type": "object"},
            }
            for t in SOFT_CONSTRAINT_TYPES
        ],
    }
