from pydantic import BaseModel
from models import RoomType
from typing import Optional

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