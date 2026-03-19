from typing import Optional

from pydantic import BaseModel
from datetime import date, time
from .models import GroupType, RoomType, AvailabilityType

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


class StudentGroupCreate(BaseModel):
    name: str
    group_type: GroupType
    department: str
    year: Optional[int] = None
    semester: Optional[int] = None
    strength: int

class StudentGroupResponse(BaseModel):
    id: int
    name: str
    group_type: GroupType
    department: str
    year: Optional[int] = None
    semester: Optional[int] = None
    strength: int
    is_active: bool

    class Config:
        from_attributes = True

class FacultyCreate(BaseModel):
    name: str
    email: str
    department: str
    max_hours_per_week: int = 20
    max_hours_per_day: int = 5

class FacultyResponse(BaseModel):
    id: int
    name: str
    email: str
    department: str
    max_hours_per_week: int
    max_hours_per_day: int
    is_active: bool

    class Config:
        from_attributes = True

class SubjectCreate(BaseModel):
    name: str
    subject_code: str
    department: str
    semester: int
    hours_per_week: int
    requires_lab: bool = False

class SubjectResponse(BaseModel):
    id: int
    name: str
    subject_code: str
    department: str
    semester: int
    hours_per_week: int
    requires_lab: bool
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

class FacultyAvailabilityCreate(BaseModel):
    faculty_id: int
    day_of_week: int  # 0=Monday, 6=Sunday
    slot_start: Optional[time] = None
    slot_end: Optional[time] = None
    availability: AvailabilityType
    reason: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

class FacultyAvailabilityResponse(BaseModel):
    id: int
    faculty_id: int
    day_of_week: int  # 0=Monday, 6=Sunday
    slot_start: Optional[time] = None
    slot_end: Optional[time] = None
    availability: AvailabilityType
    reason: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

    class Config:
        from_attributes = True