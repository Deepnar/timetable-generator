from pydantic import BaseModel
from typing import Optional

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
