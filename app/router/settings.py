"""Routes for the college-wide settings singleton (feature flags)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Admin
from app.schemas.settings import CollegeSettingsResponse, CollegeSettingsUpdate
from app.services.settings_service import get_settings, update_settings
from app.utils.auth import get_current_admin

router = APIRouter(prefix="/settings", tags=["College Settings"])


@router.get("/", response_model=CollegeSettingsResponse)
def read_settings(db: Session = Depends(get_db)):
    """Read the current feature-flag configuration."""
    return get_settings(db)


@router.put("/", response_model=CollegeSettingsResponse)
def write_settings(
    payload: CollegeSettingsUpdate,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    """Update one or more feature flags."""
    return update_settings(
        db,
        enable_lab_batches=payload.enable_lab_batches,
        allow_cross_dept_subjects=payload.allow_cross_dept_subjects,
        enable_soft_constraint_scoring=payload.enable_soft_constraint_scoring,
        config_json=payload.config_json,
    )
