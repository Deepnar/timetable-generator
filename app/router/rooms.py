from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rooms import RoomType

from ..database import get_db
from ..utils.auth import get_current_admin
from ..utils.pagination import Pagination, pagination, paginate
from ..services import redis_client
from .. import models
from .. import schemas

router = APIRouter(prefix="/rooms", tags=["Rooms"])

_ROOMS_CACHE_PREFIX = "timetable:cache:rooms"

@router.get("/", response_model=list[schemas.RoomResponse])
def get_rooms(
    response: Response,
    room_type: Optional[RoomType] = None,
    min_capacity: Optional[int] = None,
    building: Optional[str] = None,
    search: Optional[str] = None,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
):
    cache_key = (
        f"{_ROOMS_CACHE_PREFIX}:{room_type}:{min_capacity}:{building}:{search}:"
        f"{page.skip}:{page.limit}"
    )
    cached = redis_client.cache_serve_list(cache_key, response)
    if cached is not None:
        return cached
    query = select(models.Room).where(models.Room.is_active == True)
    if room_type:
        query = query.where(models.Room.room_type == room_type)
    if min_capacity is not None:
        query = query.where(models.Room.capacity >= min_capacity)
    if building:
        query = query.where(models.Room.building == building)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            models.Room.name.ilike(pattern) | models.Room.room_code.ilike(pattern)
        )
    rows = paginate(db, query, page, response)
    return redis_client.cacheable_list(
        cache_key, schemas.RoomResponse, rows, response)

@router.get("/{id}", response_model=schemas.RoomResponse)
def get_room(id: int, db: Session = Depends(get_db)):
    room = db.scalars(select(models.Room).where(models.Room.id == id)).first()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Room with id {id} not found")
    return room

@router.post("/", status_code=status.HTTP_201_CREATED,
             response_model=schemas.RoomResponse)
def create_room(room: schemas.RoomCreate, db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    new_room = models.Room(**room.model_dump())
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    redis_client.cache_delete_prefix(_ROOMS_CACHE_PREFIX)
    return new_room

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room(id: int, db: Session = Depends(get_db), current_admin: models.Admin = Depends(get_current_admin)):
    room = db.scalars(select(models.Room).where(models.Room.id == id)).first()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Room with id {id} not found")
    room.is_active = False
    db.commit()
    redis_client.cache_delete_prefix(_ROOMS_CACHE_PREFIX)
    return

@router.put("/{id}", response_model=schemas.RoomResponse)
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
    redis_client.cache_delete_prefix(_ROOMS_CACHE_PREFIX)
    return room
