from sqlalchemy import String, Boolean, Enum, Text, DateTime, ForeignKey, Integer, DECIMAL, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base
from datetime import datetime
import enum

class ScopeType(str, enum.Enum):
    DEPARTMENT = "DEPARTMENT"
    YEAR = "YEAR"
    DIVISION = "DIVISION"
    EVENT = "EVENT"
    EXAM = "EXAM"
    CUSTOM = "CUSTOM"

class ResourceType(str, enum.Enum):
    ROOM = "ROOM"
    FACULTY = "FACULTY"
    STUDENT_GROUP = "STUDENT_GROUP"
    SUBJECT = "SUBJECT"

class ParamType(str, enum.Enum):
    INT = "INT"
    FLOAT = "FLOAT"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    TIME = "TIME"
    JSON = "JSON"

class TimetableProfile(Base):
    __tablename__ = "timetable_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    scope_type: Mapped[ScopeType] = mapped_column(Enum(ScopeType))
    academic_year: Mapped[str] = mapped_column(String(10))
    semester: Mapped[int | None]
    department: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[int] = mapped_column(ForeignKey("admins.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ProfileResource(Base):
    __tablename__ = "profile_resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("timetable_profiles.id", ondelete="CASCADE"))
    resource_type: Mapped[ResourceType] = mapped_column(Enum(ResourceType))
    resource_id: Mapped[int]

class ProfileParameter(Base):
    __tablename__ = "profile_parameters"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("timetable_profiles.id", ondelete="CASCADE"))
    param_key: Mapped[str] = mapped_column(String(100))
    param_value: Mapped[str] = mapped_column(Text)
    param_type: Mapped[ParamType] = mapped_column(Enum(ParamType))
    description: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        UniqueConstraint("profile_id", "param_key", name="uq_profile_param"),
    )

class ProfileCombination(Base):
    __tablename__ = "profile_combinations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(150))
    created_by: Mapped[int] = mapped_column(ForeignKey("admins.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ProfileCombinationMember(Base):
    __tablename__ = "profile_combination_members"

    combination_id: Mapped[int] = mapped_column(
        ForeignKey("profile_combinations.id"), primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_profiles.id"), primary_key=True)
    weight: Mapped[float] = mapped_column(DECIMAL(3, 2), default=1.00)
