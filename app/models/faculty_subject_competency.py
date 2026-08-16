from sqlalchemy import (ForeignKey, String, Float, Index)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base

class FacultySubjectCompetency(Base):
    """Which faculty members may teach which subjects (A9, B4).

    Seeded by the importer from grid-derived assignments: every (faculty,
    subject) pair the published timetable assigns becomes a competency row.
    Auto-fill (``--fill-gaps``) and the solver's ``_lab_batch_faculty``
    fallback may only pick teachers who have a row here, so a practical never
    goes to someone who has not taught the subject.
    """
    __tablename__ = "faculty_subject_competency"

    __table_args__ = (
        Index("uq_faculty_subject_competency", "faculty_id", "subject_id",
              unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculty.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    # Optional preference weight (higher = preferred), collected from the
    # college by hand. NULL = competent, no preference expressed.
    preference_weight: Mapped[float | None] = mapped_column(Float, nullable=True)

    faculty = relationship("Faculty", backref="competencies")
    subject = relationship("Subject", backref="competencies")
