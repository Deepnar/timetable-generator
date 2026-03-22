from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..utils.auth import get_current_admin
from .. import models
from .. import schemas

router = APIRouter(
    prefix="/subjects",
    tags=["Subjects"]
)

@router.get("/", response_model=list[schemas.SubjectResponse])
def get_subjects(db: Session = Depends(get_db)):
    subjects = db.scalars(select(models.Subject).where(
        models.Subject.is_active == True)).all()
    return subjects

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
    return subject