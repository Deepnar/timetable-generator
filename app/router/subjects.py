from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..utils.auth import get_current_admin, require_roles
from ..utils.pagination import Pagination, pagination, paginate
from ..services import redis_client
from .. import models
from .. import schemas

router = APIRouter(
    prefix="/subjects",
    tags=["Subjects"],
    dependencies=[Depends(require_roles("admin", "hod"))]
)

_SUBJECTS_CACHE_PREFIX = "timetable:cache:subjects"

@router.get("/", response_model=list[schemas.SubjectResponse])
def get_subjects(response: Response,
    semester: Optional[int] = None,
    department: Optional[str] = None,
    requires_lab: Optional[bool] = None,
    search: Optional[str] = None,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db)):
    cache_key = (
        f"{_SUBJECTS_CACHE_PREFIX}:{semester}:{department}:{requires_lab}:{search}:"
        f"{page.skip}:{page.limit}"
    )
    cached = redis_client.cache_serve_list(cache_key, response)
    if cached is not None:
        return cached
    query = select(models.Subject).where(models.Subject.is_active == True)
    if semester is not None:
        query = query.where(models.Subject.semester == semester)
    if department:
        query = query.where(models.Subject.department == department)
    if requires_lab is not None:
        query = query.where(models.Subject.requires_lab == requires_lab)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            models.Subject.name.ilike(pattern) | models.Subject.subject_code.ilike(pattern)
        )
    rows = paginate(db, query, page, response)
    return redis_client.cacheable_list(
        cache_key, schemas.SubjectResponse, rows, response)

@router.get("/{id}", response_model=schemas.SubjectResponse)
def get_subject(id: int, db: Session = Depends(get_db)):
    subject = db.scalars(select(models.Subject).where(
        models.Subject.id == id)).first()
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Subject with id {id} not found")
    return subject

@router.post("/", status_code=status.HTTP_201_CREATED,
             response_model=schemas.SubjectResponse)
def create_subject(subject: schemas.SubjectCreate,
                   db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    existing = db.scalars(select(models.Subject).where(
        models.Subject.subject_code == subject.subject_code)).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Subject with code {subject.subject_code} already exists")
    new_subject = models.Subject(**subject.model_dump())
    db.add(new_subject)
    db.commit()
    db.refresh(new_subject)
    redis_client.cache_delete_prefix(_SUBJECTS_CACHE_PREFIX)
    return new_subject

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(id: int, db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    subject = db.scalars(select(models.Subject).where(
        models.Subject.id == id)).first()
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Subject with id {id} not found")
    subject.is_active = False
    db.commit()
    redis_client.cache_delete_prefix(_SUBJECTS_CACHE_PREFIX)
    return

@router.put("/{id}", response_model=schemas.SubjectResponse)
def update_subject(id: int, updated: schemas.SubjectCreate,
                   db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    subject = db.scalars(select(models.Subject).where(
        models.Subject.id == id)).first()
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Subject with id {id} not found")
    for key, value in updated.model_dump().items():
        setattr(subject, key, value)
    db.commit()
    db.refresh(subject)
    redis_client.cache_delete_prefix(_SUBJECTS_CACHE_PREFIX)
    return subject