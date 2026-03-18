import enum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

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