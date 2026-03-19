import enum

from sqlalchemy import Boolean, Enum, String, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, time, date, timezone

from .database import Base

class RoomType(str, enum.Enum):
    CLASSROOM = "CLASSROOM"
    LAB = "LAB"
    SEMINAR_HALL = "SEMINAR_HALL"
    AUDITORIUM = "AUDITORIUM"

class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    room_code: Mapped[str] = mapped_column(String(20), unique=True)
    room_type: Mapped[RoomType] = mapped_column(Enum(RoomType))
    capacity: Mapped[int]
    building: Mapped[str | None] = mapped_column(String(50))
    floor: Mapped[int | None]
    has_projector: Mapped[bool] = mapped_column(Boolean, default=False)
    has_ac: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class GroupType(str, enum.Enum):
    DIVISION = "DIVISION"
    BATCH = "BATCH"
    YEAR = "YEAR"
    DEPARTMENT = "DEPARTMENT"
    CUSTOM = "CUSTOM"

class StudentGroup(Base):
    __tablename__ = "student_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    group_type: Mapped[GroupType] = mapped_column(Enum(GroupType))
    department: Mapped[str] = mapped_column(String(100))
    year: Mapped[int | None]
    semester: Mapped[int | None]
    strength: Mapped[int]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Faculty(Base):
    __tablename__ = "faculty"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(100), unique=True)
    department: Mapped[str] = mapped_column(String(100))
    max_hours_per_week: Mapped[int] = mapped_column(default=20)
    max_hours_per_day: Mapped[int] = mapped_column(default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    subject_code: Mapped[str] = mapped_column(String(20), unique=True)
    department: Mapped[str] = mapped_column(String(100))
    semester: Mapped[int]
    hours_per_week: Mapped[int]
    requires_lab: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class RoomBlackouts(Base):
    __tablename__ = "room_blackouts"

    id : Mapped[int] = mapped_column(primary_key=True, nullable=False)
    room_id : Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    date : Mapped[date] = mapped_column(Date, nullable=False)  
    slot_start: Mapped[time | None] = mapped_column(nullable=True)
    slot_end: Mapped[time | None] = mapped_column(nullable=True)
    reason : Mapped[str | None] = mapped_column(String(255), nullable=True) 

class AvailabilityType(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    PREFFERED = "PREFERRED"

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