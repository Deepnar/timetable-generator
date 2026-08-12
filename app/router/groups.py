from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.groups import GroupType

from ..database import get_db
from ..utils.auth import get_current_admin, require_roles
from ..utils.pagination import Pagination, pagination, paginate
from .. import models
from .. import schemas

router = APIRouter(
    prefix="/groups",
    tags=["Student Groups"],
    dependencies=[Depends(require_roles("admin", "hod"))]
)

@router.get("/", response_model=list[schemas.StudentGroupResponse])
def get_groups(response: Response,
    year: Optional[int] = None,
    department: Optional[str] = None,
    group_type: Optional[GroupType] = None,
    search: Optional[str] = None,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db)):
    query = select(models.StudentGroup).where(models.StudentGroup.is_active == True)
    if year is not None:
        query = query.where(models.StudentGroup.year == year)
    if department:
        query = query.where(models.StudentGroup.department == department)
    if group_type:
        query = query.where(models.StudentGroup.group_type == group_type)
    if search:
        pattern = f"%{search}%"
        query = query.where(models.StudentGroup.name.ilike(pattern))
    return paginate(db, query, page, response)

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

@router.put("/{id}", response_model=schemas.StudentGroupResponse)
def update_group(id: int, updated_group: schemas.StudentGroupCreate,
                 db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    group = db.scalars(select(models.StudentGroup).where(
        models.StudentGroup.id == id)).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Group with id {id} not found")
    for key, value in updated_group.model_dump().items():
        setattr(group, key, value)
    db.commit()
    db.refresh(group)
    return group

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
