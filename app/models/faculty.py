import enum

from sqlalchemy import String, Boolean, Enum, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column
from datetime import time, date

from ..database import Base

class AvailabilityType(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    PREFFERED = "PREFERRED"

class Faculty(Base):
    __tablename__ = "faculty"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(100), unique=True)
    department: Mapped[str] = mapped_column(String(100))
    max_hours_per_week: Mapped[int] = mapped_column(default=20)
    max_hours_per_day: Mapped[int] = mapped_column(default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class FacultyAvailability(Base):
    __tablename__ = "faculty_availability"

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(nullable=False)  # 0=Monday, 6=Sunday
    slot_start: Mapped[time | None] = mapped_column(nullable=True)
    slot_end: Mapped[time | None] = mapped_column(nullable=True)
    availability : Mapped[AvailabilityType] = mapped_column(Enum(AvailabilityType), nullable=False)
    reason : Mapped[str | None] = mapped_column(String(255), nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=False)
