from pydantic import BaseModel, Field, model_validator
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
    # Free-form equipment/feature tags (e.g. ["projector", "whiteboard"]).
    equipment_json: Optional[list] = None

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
    equipment_json: Optional[list] = None
    is_active: bool

    class Config:
        from_attributes = True

class RoomBlackoutCreate(BaseModel):
    room_id: int
    # Provide EITHER a specific date OR a recurring weekday (0=Mon .. 6=Sun).
    date: Optional[date] = None
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    # Omit both times for an all-day blackout.
    slot_start: Optional[time] = None
    slot_end: Optional[time] = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _require_date_or_weekday(self):
        if self.date is None and self.day_of_week is None:
            raise ValueError("either 'date' or 'day_of_week' is required")
        return self

class RoomBlackoutResponse(BaseModel):
    id: int
    room_id: int
    date: Optional[date] = None
    day_of_week: Optional[int] = None
    slot_start: Optional[time] = None
    slot_end: Optional[time] = None
    reason: Optional[str] = None

    class Config:
        from_attributes = True
