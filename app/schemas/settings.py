"""Pydantic schemas for the college-wide settings singleton."""
from pydantic import BaseModel
from typing import Any, Optional


class CollegeSettingsResponse(BaseModel):
    id: int
    enable_lab_batches: bool
    allow_cross_dept_subjects: bool
    enable_soft_constraint_scoring: bool
    config_json: Optional[dict[str, Any]] = None

    class Config:
        from_attributes = True


class CollegeSettingsUpdate(BaseModel):
    enable_lab_batches: Optional[bool] = None
    allow_cross_dept_subjects: Optional[bool] = None
    enable_soft_constraint_scoring: Optional[bool] = None
    config_json: Optional[dict[str, Any]] = None
