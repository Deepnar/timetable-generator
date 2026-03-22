from sqlalchemy import String, Boolean, Enum, JSON, ForeignKey, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base
import enum

class ConstraintType(str, enum.Enum):
    # Hard
    NO_TEACHER_DOUBLE_BOOK = "NO_TEACHER_DOUBLE_BOOK"
    NO_ROOM_DOUBLE_BOOK = "NO_ROOM_DOUBLE_BOOK"
    NO_GROUP_DOUBLE_BOOK = "NO_GROUP_DOUBLE_BOOK"
    ROOM_CAPACITY_SUFFICIENT = "ROOM_CAPACITY_SUFFICIENT"
    ROOM_TYPE_MATCH = "ROOM_TYPE_MATCH"
    RESPECT_TEACHER_UNAVAILABILITY = "RESPECT_TEACHER_UNAVAILABILITY"
    RESPECT_ROOM_BLACKOUT = "RESPECT_ROOM_BLACKOUT"
    CONTIGUOUS_LAB_SLOTS = "CONTIGUOUS_LAB_SLOTS"
    EXAM_DATE_SEPARATION = "EXAM_DATE_SEPARATION"
    # Soft
    TEACHER_PREFERS_MORNING = "TEACHER_PREFERS_MORNING"
    AVOID_CONSECUTIVE_SAME_SUBJECT = "AVOID_CONSECUTIVE_SAME_SUBJECT"
    MINIMIZE_STUDENT_FREE_SLOTS = "MINIMIZE_STUDENT_FREE_SLOTS"
    MINIMIZE_TEACHER_FREE_SLOTS = "MINIMIZE_TEACHER_FREE_SLOTS"
    DISTRIBUTE_SUBJECTS_EVENLY = "DISTRIBUTE_SUBJECTS_EVENLY"
    BALANCE_TEACHER_LOAD = "BALANCE_TEACHER_LOAD"

class HardConstraint(Base):
    __tablename__ = "hard_constraints"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_profiles.id"), nullable=True)
    constraint_type: Mapped[ConstraintType] = mapped_column(
        Enum(ConstraintType))
    config_json: Mapped[dict | None] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class SoftConstraint(Base):
    __tablename__ = "soft_constraints"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_profiles.id"), nullable=True)
    constraint_type: Mapped[ConstraintType] = mapped_column(
        Enum(ConstraintType))
    config_json: Mapped[dict | None] = mapped_column(JSON)
    weight: Mapped[float] = mapped_column(DECIMAL(4, 2), default=1.00)
    description: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
