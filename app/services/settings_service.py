"""Helpers to read/write the college settings singleton.

The table is a singleton (id=1) so the engine, routers, and any future
background jobs can all call ``get_settings()`` to know which optional
features are enabled for this college.
"""
from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session

from app.models.settings import CollegeSettings

SINGLETON_ID = 1


def get_settings(db: Session) -> CollegeSettings:
    """Return the (single) CollegeSettings row, creating it with defaults
    if it does not yet exist."""
    settings = db.get(CollegeSettings, SINGLETON_ID)
    if settings is None:
        settings = CollegeSettings(
            id=SINGLETON_ID,
            enable_lab_batches=False,
            allow_cross_dept_subjects=False,
            enable_soft_constraint_scoring=True,
            config_json={},
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def update_settings(
    db: Session,
    *,
    enable_lab_batches: Optional[bool] = None,
    allow_cross_dept_subjects: Optional[bool] = None,
    enable_soft_constraint_scoring: Optional[bool] = None,
    config_json: Optional[dict] = None,
) -> CollegeSettings:
    """Update one or more flags. None means "leave unchanged"."""
    settings = get_settings(db)
    if enable_lab_batches is not None:
        settings.enable_lab_batches = enable_lab_batches
    if allow_cross_dept_subjects is not None:
        settings.allow_cross_dept_subjects = allow_cross_dept_subjects
    if enable_soft_constraint_scoring is not None:
        settings.enable_soft_constraint_scoring = enable_soft_constraint_scoring
    if config_json is not None:
        settings.config_json = config_json
    db.commit()
    db.refresh(settings)
    return settings
