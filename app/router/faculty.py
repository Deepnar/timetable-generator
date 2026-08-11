from typing_extensions import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..utils.auth import get_current_admin
from ..utils.pagination import Pagination, pagination, paginate
from .. import models
from .. import schemas


router = APIRouter(
    prefix="/faculty",
    tags=["Faculty"]
)

@router.get("/", response_model=list[schemas.FacultyResponse])
def get_faculty(response: Response,
                department: Optional[str] = None,
                search: Optional[str] = None,
                page: Pagination = Depends(pagination),
                db: Session = Depends(get_db)):
    query = select(models.Faculty).where(models.Faculty.is_active == True)
    if department:
        query = query.where(models.Faculty.department == department)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            models.Faculty.name.ilike(pattern) | models.Faculty.email.ilike(pattern)
        )
    return paginate(db, query, page, response)

@router.get("/{id}", response_model=schemas.FacultyResponse)
def get_one_faculty(id: int, db: Session = Depends(get_db)):
    faculty = db.scalars(select(models.Faculty).where(
        models.Faculty.id == id)).first()
    if not faculty:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Faculty with id {id} not found")
    return faculty

@router.post("/", status_code=status.HTTP_201_CREATED,
             response_model=schemas.FacultyResponse)
def create_faculty(faculty: schemas.FacultyCreate,
                   db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    existing = db.scalars(select(models.Faculty).where(
        models.Faculty.email == faculty.email)).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Faculty with email {faculty.email} already exists")
    new_faculty = models.Faculty(**faculty.model_dump())
    db.add(new_faculty)
    db.commit()
    db.refresh(new_faculty)
    return new_faculty

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faculty(id: int, db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    faculty = db.scalars(select(models.Faculty).where(
        models.Faculty.id == id)).first()
    if not faculty:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Faculty with id {id} not found")
    faculty.is_active = False
    db.commit()
    return

@router.put("/{id}", response_model=schemas.FacultyResponse)
def update_faculty(id: int, updated: schemas.FacultyCreate,
                   db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    faculty = db.scalars(select(models.Faculty).where(
        models.Faculty.id == id)).first()
    if not faculty:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Faculty with id {id} not found")
    for key, value in updated.model_dump().items():
        setattr(faculty, key, value)
    db.commit()
    db.refresh(faculty)
    return faculty