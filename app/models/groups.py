import enum

from sqlalchemy import String, Boolean, Enum, ForeignKey
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
    # Home rooms: the venue(s) the division normally holds lectures in
    # (A5). The solver hard-restricts non-lab sessions to these rooms so a
    # division no longer scatters across the whole pool. Nullable so generic
    # colleges that do not track a home room keep the legacy free-pool
    # behaviour.
    home_room_id: Mapped[int | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    home_room_secondary_id: Mapped[int | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
