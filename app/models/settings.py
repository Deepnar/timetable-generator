from sqlalchemy import Boolean, String, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base

class CollegeSettings(Base):
    """
    Singleton table for college-wide feature flags and configurations.
    Allows colleges to toggle optional features like lab batches or cross-dept subjects.
    """
    __tablename__ = "college_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Feature Flags
    enable_lab_batches: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_cross_dept_subjects: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_soft_constraint_scoring: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Global Configurations
    config_json: Mapped[str | None] = mapped_column(JSON, nullable=True)
