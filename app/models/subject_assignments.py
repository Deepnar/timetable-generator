from sqlalchemy import ForeignKey, Integer, Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base

class SubjectAssignment(Base):
    """
    Maps a subject to a specific faculty member and student group.
    Handles cross-department subjects and shared teaching loads (e.g., 80/20 splits).
    """
    __tablename__ = "subject_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # The core mapping triad
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="SET NULL"), nullable=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("student_groups.id", ondelete="CASCADE"), nullable=False)
    
    # How many hours per week this specific assignment needs
    weekly_hours: Mapped[int] = mapped_column(nullable=False, default=1)
    
    # Load share (e.g., 0.8 for 80% load share if multiple teachers share a subject)
    load_share: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # Relationships for easy querying
    subject = relationship("Subject", backref="assignments")
    faculty = relationship("Faculty", backref="subject_assignments")
    group = relationship("StudentGroup", backref="subject_assignments")
