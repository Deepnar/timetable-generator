from pydantic import BaseModel
from ..models.constraints import ConstraintType
from typing import Optional, Any

class HardConstraintCreate(BaseModel):
    profile_id: Optional[int] = None
    constraint_type: ConstraintType
    config_json: Optional[dict] = None
    description: Optional[str] = None

class HardConstraintResponse(BaseModel):
    id: int
    profile_id: Optional[int] = None
    constraint_type: ConstraintType
    config_json: Optional[dict] = None
    description: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True

class SoftConstraintCreate(BaseModel):
    profile_id: Optional[int] = None
    constraint_type: ConstraintType
    config_json: Optional[dict] = None
    weight: float = 1.00
    description: Optional[str] = None

class SoftConstraintResponse(BaseModel):
    id: int
    profile_id: Optional[int] = None
    constraint_type: ConstraintType
    config_json: Optional[dict] = None
    weight: float
    description: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True
