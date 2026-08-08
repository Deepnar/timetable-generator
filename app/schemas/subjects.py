from pydantic import BaseModel
from typing import Optional

class SubjectCreate(BaseModel):
    name: str
    subject_code: str
    department: str
    semester: int
    hours_per_week: int
    requires_lab: bool = False
    # Declarative room requirements (room_types / min_capacity / features /
    # session_type); overrides requires_lab when set.
    requirements_json: Optional[dict] = None

class SubjectResponse(BaseModel):
    id: int
    name: str
    subject_code: str
    department: str
    semester: int
    hours_per_week: int
    requires_lab: bool
    requirements_json: Optional[dict] = None
    is_active: bool

    class Config:
        from_attributes = True
