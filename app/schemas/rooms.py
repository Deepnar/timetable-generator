from pydantic import BaseModel
from typing import Optional
from datetime import date, time

from ..models.rooms import RoomType

class RoomCreate(BaseModel):
    name: str
    room_code: str
    room_type: RoomType
    capacity: int
    building: Optional[str] = None
    floor: Optional[int] = None
    has_projector: bool = False
    has_ac: bool = False

class RoomResponse(BaseModel):
    id: int
    name: str
    room_code: str
    room_type: RoomType
    capacity: int
    building: Optional[str] = None
    floor: Optional[int] = None
    has_projector: bool
    has_ac: bool
    is_active: bool

    class Config:
        from_attributes = True

class RoomBlackoutCreate(BaseModel):
    room_id: int
    date: date
    slot_start: time
    slot_end: time
    reason: Optional[str] = None

class RoomBlackoutResponse(BaseModel):
    id: int
    room_id: int
    date: date
    slot_start: time
    slot_end: time
    reason: Optional[str] = None

    class Config:
        from_attributes = True
