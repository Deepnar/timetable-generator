from sqlalchemy import String, Enum, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from datetime import datetime
import enum

class ArchiveReason(str, enum.Enum):
    YEAR_RESET = "YEAR_RESET"
    SEMESTER_END = "SEMESTER_END"
    MANUAL = "MANUAL"
    SUPERSEDED = "SUPERSEDED"

class ResetType(str, enum.Enum):
    FULL_YEAR = "FULL_YEAR"
    SEMESTER = "SEMESTER"
    PROFILE_SPECIFIC = "PROFILE_SPECIFIC"

class TimetableHistory(Base):
    __tablename__ = "timetable_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_instance_id: Mapped[int]
    academic_year: Mapped[str] = mapped_column(String(10))
    semester: Mapped[int | None]
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    archived_by: Mapped[int] = mapped_column(ForeignKey("admins.id"))
    archived_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
    archive_reason: Mapped[ArchiveReason] = mapped_column(
        Enum(ArchiveReason))

class TimetableResetLog(Base):
    __tablename__ = "timetable_reset_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    reset_type: Mapped[ResetType] = mapped_column(Enum(ResetType))
    academic_year: Mapped[str] = mapped_column(String(10))
    profiles_reset: Mapped[dict | None] = mapped_column(JSON)
    reset_by: Mapped[int] = mapped_column(ForeignKey("admins.id"))
    reset_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
    notes: Mapped[str | None] = mapped_column(Text)
