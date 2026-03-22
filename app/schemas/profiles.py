from pydantic import BaseModel
from ..models.profiles import ScopeType, ResourceType, ParamType
from typing import Optional
from datetime import datetime

class ProfileCreate(BaseModel):
    name: str
    description: Optional[str] = None
    scope_type: ScopeType
    academic_year: str
    semester: Optional[int] = None
    department: Optional[str] = None

class ProfileResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    scope_type: ScopeType
    academic_year: str
    semester: Optional[int] = None
    department: Optional[str] = None
    is_active: bool
    is_archived: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ProfileResourceCreate(BaseModel):
    resource_type: ResourceType
    resource_id: int

class ProfileResourceResponse(BaseModel):
    id: int
    profile_id: int
    resource_type: ResourceType
    resource_id: int

    class Config:
        from_attributes = True

class ProfileParameterCreate(BaseModel):
    param_key: str
    param_value: str
    param_type: ParamType
    description: Optional[str] = None

class ProfileParameterResponse(BaseModel):
    id: int
    profile_id: int
    param_key: str
    param_value: str
    param_type: ParamType
    description: Optional[str] = None

    class Config:
        from_attributes = True

class ProfileCombinationCreate(BaseModel):
    name: Optional[str] = None
    profile_ids: list[int]
    weights: Optional[list[float]] = None

class ProfileCombinationResponse(BaseModel):
    id: int
    name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
