from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.groups import GroupType

from ..database import get_db
from ..utils.auth import get_current_admin
from .. import models
from .. import schemas

router = APIRouter(
    prefix="/groups",
    tags=["Student Groups"]
)

@router.get("/", response_model=list[schemas.StudentGroupResponse])
def get_groups(year: Optional[int] = None,
    department: Optional[str] = None,
    group_type: Optional[GroupType] = None,
    db: Session = Depends(get_db)):
    query = select(models.StudentGroup).where(models.StudentGroup.is_active == True)
    if year is not None:
        query = query.where(models.StudentGroup.year == year)
    if department:
        query = query.where(models.StudentGroup.department == department)
    if group_type:
        query = query.where(models.StudentGroup.group_type == group_type)
    groups = db.scalars(query).all()
    return groups

@router.get("/{id}", response_model=schemas.StudentGroupResponse)
def get_group(id: int, db: Session = Depends(get_db)):
    group = db.scalars(select(models.StudentGroup).where(
        models.StudentGroup.id == id)).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Group with id {id} not found")
    return group

@router.post("/", status_code=status.HTTP_201_CREATED,
             response_model=schemas.StudentGroupResponse)
def create_group(group: schemas.StudentGroupCreate,
                 db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    new_group = models.StudentGroup(**group.model_dump())
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(id: int, db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    group = db.scalars(select(models.StudentGroup).where(
        models.StudentGroup.id == id)).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Group with id {id} not found")
    group.is_active = False
    db.commit()
    return
