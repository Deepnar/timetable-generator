import enum

from sqlalchemy import String, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

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
    incharge_email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Student-portal link: the login email of a student who should see this
    # group's published timetable on /my-timetable (DD-022 #1). Nullable so
    # existing rows and CSV imports are untouched.
    student_email: Mapped[str | None] = mapped_column(String(100), nullable=True)
