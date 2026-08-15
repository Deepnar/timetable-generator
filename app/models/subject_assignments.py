from sqlalchemy import (ForeignKey, Integer, Float, String, Index, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base

class SubjectAssignment(Base):
    """
    Maps a subject to a specific faculty member and student group.
    Handles cross-department subjects and shared teaching loads (e.g., 80/20 splits).
    """
    __tablename__ = "subject_assignments"

    __table_args__ = (
        # One class, one subject, one teacher, one row. A whole-division row
        # (NULL batch/period) is unique on (subject, group) alone; batched lab
        # rows are unique per (subject, group, batch, period). Coalescing NULLs
        # to 0 is required because a plain unique index would let duplicate
        # NULL batch rows coexist (Postgres treats NULLs as distinct).
        Index(
            "uq_subject_assignments_subject_group_batch_period",
            "subject_id", "group_id",
            text("coalesce(batch_number, 0)"),
            text("coalesce(period_number, 0)"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # The core mapping triad
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="SET NULL"), nullable=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("student_groups.id", ondelete="CASCADE"), nullable=False)
    
    # How many hours per week this specific assignment needs
    weekly_hours: Mapped[int] = mapped_column(nullable=False, default=1)
    
    # Load share (e.g., 0.8 for 80% load share if multiple teachers share a subject)
    load_share: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # Which lab batch this assignment's faculty handles (1..N), when a lab
    # subject runs as parallel practicals. NULL = the assignment covers the
    # whole division (lectures/tutorials, or a non-batched lab). Parallel labs
    # need one row per batch (each with a distinct faculty), matching the real
    # timetable cells ("Lab CG D1 D2 SuS/PD").
    batch_number: Mapped[int | None] = mapped_column(nullable=True)

    # Which weekly period (1..N) of a lab subject this batch row belongs to.
    # A lab runs several parallel practicals a week (TE CG: D1D2 one day,
    # D3D4 another); ``batch_number`` is a global batch id so it cannot
    # separate periods on its own. NULL = single-period / non-batched.
    period_number: Mapped[int | None] = mapped_column(nullable=True)

    # Relationships for easy querying
    subject = relationship("Subject", backref="assignments")
    faculty = relationship("Faculty", backref="subject_assignments")
    group = relationship("StudentGroup", backref="subject_assignments")
