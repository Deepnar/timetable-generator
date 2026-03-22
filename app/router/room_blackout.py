from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..utils.auth import get_current_admin
from .. import models
from .. import schemas

router = APIRouter(prefix="/blackouts", tags=["Room Blackouts"])

@router.post("/", status_code=status.HTTP_201_CREATED,response_model=schemas.RoomBlackoutResponse)
def create_room_blackout(blackout: schemas.RoomBlackoutCreate, db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    new_blackout = models.RoomBlackout(**blackout.model_dump())
    db.add(new_blackout)
    db.commit()
    db.refresh(new_blackout)
    return new_blackout

@router.get("/", response_model=list[schemas.RoomBlackoutResponse])
def get_room_blackouts(db: Session = Depends(get_db)):
    blackouts = db.scalars(select(models.RoomBlackout)).all()
    return blackouts

@router.get("/{id}", response_model=schemas.RoomBlackoutResponse)
def get_room_blackout(id: int, db: Session = Depends(get_db)):
    blackout = db.scalars(select(models.RoomBlackout).where(models.RoomBlackout.id == id)).first()
    if not blackout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Room blackout with id {id} not found")
    return blackout

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room_blackout(id: int, db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    blackout = db.scalars(select(models.RoomBlackout).where(models.RoomBlackout.id == id)).first()
    if not blackout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Room blackout with id {id} not found")
    db.delete(blackout)
    db.commit()
    return

@router.put("/{id}", response_model=schemas.RoomBlackoutResponse)
def update_room_blackout(id: int, updated_blackout: schemas.RoomBlackoutCreate,
                db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    blackout = db.scalars(select(models.RoomBlackout).where(models.RoomBlackout.id == id)).first()
    if not blackout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Room blackout with id {id} not found")
    for key, value in updated_blackout.model_dump().items():
        setattr(blackout, key, value)
    db.commit()
    db.refresh(blackout)
    return blackout
