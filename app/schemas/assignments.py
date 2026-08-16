"""Schemas for the Subject-Faculty-Group mapping triad."""
from pydantic import BaseModel, Field
from typing import Optional


class SubjectAssignmentCreate(BaseModel):
    subject_id: int
    faculty_id: Optional[int] = None
    group_id: int
    weekly_hours: int = Field(default=1, ge=1, le=40)
    load_share: float = Field(default=1.0, ge=0.0, le=1.0)
    # How many of the weekly_hours are TUTORIAL sessions (DD-046); None means
    # the row has no tutorial stream.
    tutorial_hours: Optional[int] = Field(default=None, ge=0, le=40)


class SubjectAssignmentUpdate(BaseModel):
    faculty_id: Optional[int] = None
    weekly_hours: Optional[int] = Field(default=None, ge=1, le=40)
    load_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    tutorial_hours: Optional[int] = Field(default=None, ge=0, le=40)


class SubjectAssignmentResponse(BaseModel):
    id: int
    subject_id: int
    faculty_id: Optional[int]
    group_id: int
    weekly_hours: int
    load_share: float
    # Demand provenance: GRID | SCHEME | AUTOFILL (set by the importer); None
    # for rows created through the API by hand.
    source: Optional[str] = None
    tutorial_hours: Optional[int] = None

    class Config:
        from_attributes = True
