from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..utils.auth import get_current_admin
from .. import models
from .. import schemas

router = APIRouter(prefix="/rooms", tags=["Rooms"])

@router.get("/rooms", response_model=list[schemas.RoomResponse])
def get_rooms(db: Session = Depends(get_db)):
    rooms = db.scalars(select(models.Room).where(models.Room.is_active == True)).all()
    return rooms

@router.get("/rooms/{id}", response_model=schemas.RoomResponse)
def get_room(id: int, db: Session = Depends(get_db)):
    room = db.scalars(select(models.Room).where(models.Room.id == id)).first()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Room with id {id} not found")
    return room

@router.post("/rooms", status_code=status.HTTP_201_CREATED,
             response_model=schemas.RoomResponse)
def create_room(room: schemas.RoomCreate, db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    new_room = models.Room(**room.model_dump())
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    return new_room

@router.delete("/rooms/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room(id: int, db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    room = db.scalars(select(models.Room).where(models.Room.id == id)).first()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Room with id {id} not found")
    room.is_active = False
    db.commit()
    return

@router.put("/rooms/{id}", response_model=schemas.RoomResponse)
def update_room(id: int, updated_room: schemas.RoomCreate,
                db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    room = db.scalars(select(models.Room).where(models.Room.id == id)).first()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Room with id {id} not found")
    for key, value in updated_room.model_dump().items():
        setattr(room, key, value)
    db.commit()
    db.refresh(room)
    return room
