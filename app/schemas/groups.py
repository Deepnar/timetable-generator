from pydantic import BaseModel
from typing import Optional

from ..models.groups import GroupType

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
