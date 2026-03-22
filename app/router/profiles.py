from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional
from ..database import get_db
from ..models.profiles import (TimetableProfile, ProfileResource,
                                  ProfileParameter, ProfileCombination,
                                  ProfileCombinationMember, ScopeType)
from ..models import Admin
from ..schemas.profiles import (ProfileCreate, ProfileResponse,
                                   ProfileResourceCreate, ProfileResourceResponse,
                                   ProfileParameterCreate, ProfileParameterResponse,
                                   ProfileCombinationCreate, ProfileCombinationResponse)
from ..utils.auth import get_current_admin

router = APIRouter(prefix="/profiles", tags=["Profiles"])

# ── Profile CRUD ──────────────────────────────────────────

@router.get("/", response_model=list[ProfileResponse])
def get_profiles(
    academic_year: Optional[str] = None,
    scope_type: Optional[ScopeType] = None,
    department: Optional[str] = None,
    is_archived: bool = False,
    db: Session = Depends(get_db)
):
    query = select(TimetableProfile).where(
        TimetableProfile.is_active == True,
        TimetableProfile.is_archived == is_archived
    )
    if academic_year:
        query = query.where(TimetableProfile.academic_year == academic_year)
    if scope_type:
        query = query.where(TimetableProfile.scope_type == scope_type)
    if department:
        query = query.where(TimetableProfile.department == department)
    return db.scalars(query).all()

@router.get("/{id}", response_model=ProfileResponse)
def get_profile(id: int, db: Session = Depends(get_db)):
    profile = db.scalars(
        select(TimetableProfile).where(TimetableProfile.id == id)
    ).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Profile {id} not found")
    return profile

@router.post("/", status_code=status.HTTP_201_CREATED,
             response_model=ProfileResponse)
def create_profile(
    profile: ProfileCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    new_profile = TimetableProfile(
        **profile.model_dump(),
        created_by=current_admin.id
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    return new_profile

@router.put("/{id}", response_model=ProfileResponse)
def update_profile(
    id: int,
    updated: ProfileCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    profile = db.scalars(
        select(TimetableProfile).where(TimetableProfile.id == id)
    ).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Profile {id} not found")
    for key, value in updated.model_dump().items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_profile(
    id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    profile = db.scalars(
        select(TimetableProfile).where(TimetableProfile.id == id)
    ).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Profile {id} not found")
    profile.is_archived = True
    profile.is_active = False
    db.commit()
    return

# ── Profile Resources ─────────────────────────────────────

@router.get("/{id}/resources",
            response_model=list[ProfileResourceResponse])
def get_profile_resources(id: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(ProfileResource).where(ProfileResource.profile_id == id)
    ).all()

@router.post("/{id}/resources",
             status_code=status.HTTP_201_CREATED,
             response_model=ProfileResourceResponse)
def add_resource_to_profile(
    id: int,
    resource: ProfileResourceCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    profile = db.scalars(
        select(TimetableProfile).where(TimetableProfile.id == id)
    ).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Profile {id} not found")
    new_resource = ProfileResource(
        profile_id=id,
        **resource.model_dump()
    )
    db.add(new_resource)
    db.commit()
    db.refresh(new_resource)
    return new_resource

@router.delete("/{id}/resources/{resource_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def remove_resource_from_profile(
    id: int,
    resource_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    resource = db.scalars(
        select(ProfileResource).where(
            ProfileResource.id == resource_id,
            ProfileResource.profile_id == id
        )
    ).first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Resource not found in this profile")
    db.delete(resource)
    db.commit()
    return

# ── Profile Parameters ────────────────────────────────────

@router.get("/{id}/parameters",
            response_model=list[ProfileParameterResponse])
def get_profile_parameters(id: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(ProfileParameter).where(ProfileParameter.profile_id == id)
    ).all()

@router.post("/{id}/parameters",
             status_code=status.HTTP_201_CREATED,
             response_model=ProfileParameterResponse)
def set_parameter(
    id: int,
    param: ProfileParameterCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    existing = db.scalars(
        select(ProfileParameter).where(
            ProfileParameter.profile_id == id,
            ProfileParameter.param_key == param.param_key
        )
    ).first()
    if existing:
        for key, value in param.model_dump().items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    new_param = ProfileParameter(profile_id=id, **param.model_dump())
    db.add(new_param)
    db.commit()
    db.refresh(new_param)
    return new_param

@router.delete("/{id}/parameters/{param_key}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_parameter(
    id: int,
    param_key: str,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    param = db.scalars(
        select(ProfileParameter).where(
            ProfileParameter.profile_id == id,
            ProfileParameter.param_key == param_key
        )
    ).first()
    if not param:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Parameter {param_key} not found")
    db.delete(param)
    db.commit()
    return

# ── Profile Combinations ──────────────────────────────────

@router.post("/combine",
             status_code=status.HTTP_201_CREATED,
             response_model=ProfileCombinationResponse)
def combine_profiles(
    combo: ProfileCombinationCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    new_combo = ProfileCombination(
        name=combo.name,
        created_by=current_admin.id
    )
    db.add(new_combo)
    db.flush()

    weights = combo.weights or [1.0] * len(combo.profile_ids)
    for profile_id, weight in zip(combo.profile_ids, weights):
        member = ProfileCombinationMember(
            combination_id=new_combo.id,
            profile_id=profile_id,
            weight=weight
        )
        db.add(member)

    db.commit()
    db.refresh(new_combo)
    return new_combo
