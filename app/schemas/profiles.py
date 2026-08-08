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

class ProfileCombinationMemberResponse(BaseModel):
    profile_id: int
    profile_name: Optional[str] = None
    weight: float
    is_active: bool

class ProfileCombinationListResponse(BaseModel):
    id: int
    name: Optional[str] = None
    created_at: datetime
    members: list[ProfileCombinationMemberResponse]
    resolution_status: str

class ResolvedConstraint(BaseModel):
    """One merged hard/soft constraint row in a resolved preview."""
    id: int
    profile_id: Optional[int] = None
    constraint_type: str
    config_json: Optional[dict] = None
    description: Optional[str] = None
    is_active: bool
    weight: Optional[float] = None  # soft constraints only

class ProfileCombinationResolveResponse(BaseModel):
    """The merged view the solvers would consume for a combination run.

    Mirrors ``app/engine/profile_resolver.ResolvedProfile`` so an admin can
    preview what a ``POST /generate`` combination run will actually schedule.
    """
    combination_id: int
    source_profile_ids: list[int]
    params: dict
    resources: dict[str, list[int]]
    hard_constraints: list[ResolvedConstraint]
    soft_constraints: list[ResolvedConstraint]
