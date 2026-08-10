"""Routes for the college-wide settings singleton (feature flags)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Admin
from app.schemas.settings import CollegeSettingsResponse, CollegeSettingsUpdate
from app.services.settings_service import get_settings, update_settings
from app.services import redis_client
from app.utils.auth import get_current_admin

router = APIRouter(prefix="/settings", tags=["College Settings"])

_SETTINGS_CACHE_KEY = "timetable:cache:settings"


@router.get("/", response_model=CollegeSettingsResponse)
def read_settings(db: Session = Depends(get_db)):
    """Read the current feature-flag configuration (cached briefly)."""
    cached = redis_client.cache_get_json(_SETTINGS_CACHE_KEY)
    if cached is not None:
        return cached
    row = get_settings(db)
    body = CollegeSettingsResponse.model_validate(row).model_dump(mode="json")
    redis_client.cache_set_json(_SETTINGS_CACHE_KEY, body)
    return body


@router.put("/", response_model=CollegeSettingsResponse)
def write_settings(
    payload: CollegeSettingsUpdate,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    """Update one or more feature flags."""
    redis_client.cache_delete_prefix(_SETTINGS_CACHE_KEY)
    return update_settings(
        db,
        enable_lab_batches=payload.enable_lab_batches,
        allow_cross_dept_subjects=payload.allow_cross_dept_subjects,
        enable_soft_constraint_scoring=payload.enable_soft_constraint_scoring,
        config_json=payload.config_json,
    )
