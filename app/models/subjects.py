from sqlalchemy import String, Boolean, JSON
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
    # Declarative room requirements (room_types / min_capacity / features /
    # session_type); overrides requires_lab when set. See
    # app/engine/resource_requirements.py for the match semantics.
    requirements_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
