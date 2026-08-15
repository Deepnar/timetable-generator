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
    incharge_email: Optional[str] = None
    home_room_id: Optional[int] = None
    home_room_secondary_id: Optional[int] = None

class StudentGroupResponse(BaseModel):
    id: int
    name: str
    group_type: GroupType
    department: str
    year: Optional[int] = None
    semester: Optional[int] = None
    strength: int
    is_active: bool
    incharge_email: Optional[str] = None
    home_room_id: Optional[int] = None
    home_room_secondary_id: Optional[int] = None

    class Config:
        from_attributes = True
