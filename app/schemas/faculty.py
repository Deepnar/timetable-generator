from pydantic import BaseModel
from typing import Optional
from datetime import date, time

from ..models.faculty import AvailabilityType

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
