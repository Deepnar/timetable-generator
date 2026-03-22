from pydantic import BaseModel
from app.models.generation import (TimetableType, GenerationStatus,
                                    InstanceStatus, SessionType, AlgorithmType)
from typing import Optional
from datetime import datetime, date, time

class GenerationRequest(BaseModel):
    profile_id: Optional[int] = None
    combination_id: Optional[int] = None
    academic_year: str
    semester: Optional[int] = None
    timetable_type: TimetableType
    instances_requested: int = 3
    algorithm: AlgorithmType = AlgorithmType.GREEDY

class GenerationResponse(BaseModel):
    id: int
    profile_id: Optional[int] = None
    combination_id: Optional[int] = None
    academic_year: str
    semester: Optional[int] = None
    timetable_type: TimetableType
    generation_status: GenerationStatus
    algorithm_used: AlgorithmType
    instances_requested: int
    instances_produced: int
    triggered_at: datetime
    completed_at: Optional[datetime] = None
    error_log: Optional[str] = None

    class Config:
        from_attributes = True

class InstanceResponse(BaseModel):
    id: int
    generation_id: int
    instance_number: int
    label: Optional[str] = None
    soft_score: Optional[float] = None
    hard_violations: int
    status: InstanceStatus
    selected_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True

class SlotResponse(BaseModel):
    id: int
    instance_id: int
    slot_date: Optional[date] = None
    day_of_week: Optional[int] = None
    slot_number: int
    start_time: time
    end_time: time
    subject_id: Optional[int] = None
    faculty_id: Optional[int] = None
    room_id: Optional[int] = None
    student_group_id: Optional[int] = None
    session_type: SessionType
    is_manual_override: bool
    override_reason: Optional[str] = None
    external_speaker: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True

class SlotOverride(BaseModel):
    day_of_week: Optional[int] = None
    slot_number: Optional[int] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    room_id: Optional[int] = None
    faculty_id: Optional[int] = None
    override_reason: str
