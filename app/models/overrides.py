from datetime import datetime, date

from sqlalchemy import (Enum, Integer, Date, DateTime, ForeignKey, Text)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
import enum


class OverrideType(str, enum.Enum):
    """The kind of mid-year change recorded against a published timetable."""
    TEACHER_COVER = "TEACHER_COVER"
    ROOM_CHANGE = "ROOM_CHANGE"
    SWAP = "SWAP"
    TEMP = "TEMP"
    CUSTOM = "CUSTOM"


class TimetableOverride(Base):
    """A manual mid-year change to a published/locked timetable.

    Published timetables are normally immutable (re-generation is the
    workflow), but real colleges need in-term edits: a teacher leaves, a room
    is unavailable, two lectures must swap, or a class runs on a temporary
    window. Each change is recorded as a row here rather than mutating the
    published slots, so the base timetable stays authoritative and the change
    set is auditable and reversible.

    ``date_from``/``date_to`` are NULL for a permanent change and set for a
    temporary window (``TEMP``); ``resolved_at`` marks a change that was
    reverted/ended (the row is kept as history). The old values are read from
    the referenced slot at apply time; the row stores only what changes.
    """
    __tablename__ = "timetable_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_instances.id", ondelete="CASCADE"))
    # The slot being changed. NULL only for a broad/temporary change that
    # covers a whole window rather than one placement.
    slot_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_slots.id", ondelete="CASCADE"), nullable=True)
    override_type: Mapped[OverrideType] = mapped_column(
        Enum(OverrideType), default=OverrideType.TEACHER_COVER)
    # Temporary window. NULL = permanent.
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    # What the change swaps in (old values come from the slot itself).
    new_faculty_id: Mapped[int | None] = mapped_column(
        ForeignKey("faculty.id", ondelete="SET NULL"), nullable=True)
    new_room_id: Mapped[int | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    # For a SWAP: the other slot this one exchanges positions with.
    swap_with_slot_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_slots.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("admins.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
