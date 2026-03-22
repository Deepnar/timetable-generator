from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..utils.auth import get_current_admin
from .. import models
from .. import schemas

router = APIRouter(
    prefix="/faculty_availability",tags=["Faculty Availability"]
)

@router.post("/", status_code=status.HTTP_201_CREATED,response_model=schemas.FacultyAvailabilityResponse)
def create_faculty_availability(availability: schemas.FacultyAvailabilityCreate, db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    new_availability = models.FacultyAvailability(**availability.model_dump())
    db.add(new_availability)
    db.commit()
    db.refresh(new_availability)
    return new_availability

@router.get("/", response_model=list[schemas.FacultyAvailabilityResponse])
def get_faculty_availability(db: Session = Depends(get_db)):
    availability = db.scalars(select(models.FacultyAvailability)).all()
    return availability

@router.get("/{id}", response_model=schemas.FacultyAvailabilityResponse)
def get_one_faculty_availability(id: int, db: Session = Depends(get_db)):
    availability = db.scalars(select(models.FacultyAvailability).where(models.FacultyAvailability.id == id)).first()
    if not availability:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Faculty availability with id {id} not found")
    return availability

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faculty_availability(id: int, db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    availability = db.scalars(select(models.FacultyAvailability).where(models.FacultyAvailability.id == id)).first()
    if not availability:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Faculty availability with id {id} not found")
    db.delete(availability)
    db.commit()
    return

@router.put("/{id}", response_model=schemas.FacultyAvailabilityResponse)
def update_faculty_availability(id: int, updated: schemas.FacultyAvailabilityCreate,
                db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    availability = db.scalars(select(models.FacultyAvailability).where(models.FacultyAvailability.id == id)).first()
    if not availability:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Faculty availability with id {id} not found")
    for key, value in updated.model_dump().items():
        setattr(availability, key, value)
    db.commit()
    db.refresh(availability)
    return availability