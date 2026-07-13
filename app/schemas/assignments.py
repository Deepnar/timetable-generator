"""Schemas for the Subject-Faculty-Group mapping triad."""
from pydantic import BaseModel, Field
from typing import Optional


class SubjectAssignmentCreate(BaseModel):
    subject_id: int
    faculty_id: Optional[int] = None
    group_id: int
    weekly_hours: int = Field(default=1, ge=1, le=40)
    load_share: float = Field(default=1.0, ge=0.0, le=1.0)


class SubjectAssignmentUpdate(BaseModel):
    faculty_id: Optional[int] = None
    weekly_hours: Optional[int] = Field(default=None, ge=1, le=40)
    load_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class SubjectAssignmentResponse(BaseModel):
    id: int
    subject_id: int
    faculty_id: Optional[int]
    group_id: int
    weekly_hours: int
    load_share: float

    class Config:
        from_attributes = True
