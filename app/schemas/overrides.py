"""Schemas for the mid-year change loop (timetable_overrides)."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
from app.models.overrides import OverrideType


class OverrideCreate(BaseModel):
    """A manual change to a published timetable.

    ``slot_id`` is the slot being changed; the old values are read from that
    slot at apply time. ``new_faculty_id``/``new_room_id`` hold what the change
    swaps in. ``swap_with_slot_id`` is set for a SWAP (the two slots exchange
    positions). ``date_from``/``date_to`` mark a temporary window (NULL =
    permanent).
    """
    slot_id: int
    override_type: OverrideType = OverrideType.TEACHER_COVER
    new_faculty_id: Optional[int] = None
    new_room_id: Optional[int] = None
    swap_with_slot_id: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    reason: Optional[str] = Field(default=None, max_length=500)


class SwapCreate(BaseModel):
    """Swap two slots within the same instance."""
    with_slot_id: int
    reason: Optional[str] = Field(default=None, max_length=500)


class OverrideResponse(BaseModel):
    id: int
    instance_id: int
    slot_id: Optional[int]
    override_type: OverrideType
    new_faculty_id: Optional[int]
    new_room_id: Optional[int]
    swap_with_slot_id: Optional[int]
    date_from: Optional[date]
    date_to: Optional[date]
    reason: Optional[str]
    created_by: Optional[int]
    resolved_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class OverrideDetail(OverrideResponse):
    """Override plus resolved display names for the change list UI."""
    slot_day: Optional[int] = None
    slot_number: Optional[int] = None
    subject_code: Optional[str] = None
    subject_name: Optional[str] = None
    group_name: Optional[str] = None
    old_faculty_name: Optional[str] = None
    new_faculty_name: Optional[str] = None
    old_room_code: Optional[str] = None
    new_room_code: Optional[str] = None


class AvailableFaculty(BaseModel):
    """A candidate teacher for covering a slot."""
    id: int
    name: str
    email: Optional[str] = None
    department: str
