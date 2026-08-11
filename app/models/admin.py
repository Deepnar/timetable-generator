from sqlalchemy import String, Boolean, Enum, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column
from datetime import time, date
import enum

from app.database import Base

class AdminRole(str, enum.Enum):
    """Role-based access control levels (DD-021).

    ``admin`` — full access (create users, edit everything, publish).
    ``hod``   — head of department; manage their department's data + generate.
    ``teacher`` — read their own schedule and exports.
    ``student`` — read their group's published timetable.
    The JWT carries the role so the middleware and role-gated dependencies can
    enforce it without a DB hit on every request.
    """
    ADMIN = "admin"
    HOD = "hod"
    TEACHER = "teacher"
    STUDENT = "student"

class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Role-based access control. Defaults to admin so existing rows and the
    # self-registration path keep working (migration ..._add_admin_role).
    # values_callable stores the lowercase enum VALUE ('admin', 'hod', ...)
    # rather than the member NAME ('ADMIN'), matching the migration's
    # server_default and the role strings written elsewhere.
    role: Mapped[AdminRole] = mapped_column(
        Enum(AdminRole, values_callable=lambda e: [m.value for m in e]),
        default=AdminRole.ADMIN)