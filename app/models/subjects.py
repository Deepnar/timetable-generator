from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

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
