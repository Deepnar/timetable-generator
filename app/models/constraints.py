from sqlalchemy import String, Boolean, JSON, ForeignKey, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base
import enum

class ConstraintType(str, enum.Enum):
    """Catalog of known constraint types.

    This is a *catalog* for input validation and discovery, not a DB enum —
    the ``constraint_type`` columns are plain strings so a new data-driven
    rule needs only a new entry here plus a validator registered in
    ``app.engine.constraint_registry`` (no schema migration).

    Tiers (Phase 3b, A10): INVARIANT rules are physics and always enforced;
    INSTITUTIONAL rules are policy that fires only from a profile/college-
    default row (a college-default set is seeded by migration); the rest are
    OPTIONAL per-profile rules. ``assert_registry_enum_parity()`` fails
    startup if this catalog and the validator registry ever drift apart.
    """
    # INVARIANT — physics (always enforced by the checker)
    NO_TEACHER_DOUBLE_BOOK = "NO_TEACHER_DOUBLE_BOOK"
    NO_ROOM_DOUBLE_BOOK = "NO_ROOM_DOUBLE_BOOK"
    NO_GROUP_DOUBLE_BOOK = "NO_GROUP_DOUBLE_BOOK"
    NO_CROSS_TIMETABLE_TEACHER_CONFLICT = "NO_CROSS_TIMETABLE_TEACHER_CONFLICT"
    NO_CROSS_TIMETABLE_ROOM_CONFLICT = "NO_CROSS_TIMETABLE_ROOM_CONFLICT"
    NO_CROSS_TIMETABLE_GROUP_CONFLICT = "NO_CROSS_TIMETABLE_GROUP_CONFLICT"
    ROOM_REQUIREMENTS_MET = "ROOM_REQUIREMENTS_MET"
    RESPECT_TEACHER_UNAVAILABILITY = "RESPECT_TEACHER_UNAVAILABILITY"
    RESPECT_ROOM_BLACKOUT = "RESPECT_ROOM_BLACKOUT"
    NO_TEACHING_IN_BREAK_SLOT = "NO_TEACHING_IN_BREAK_SLOT"
    LAB_ROTATION_COMPLETE = "LAB_ROTATION_COMPLETE"
    # INSTITUTIONAL — policy; fires only from a profile/college-default row.
    SAME_SUBJECT_SAME_DAY = "SAME_SUBJECT_SAME_DAY"
    MAX_ONE_LAB_PER_DAY = "MAX_ONE_LAB_PER_DAY"
    CROSS_DEPT_DAILY_CAP = "CROSS_DEPT_DAILY_CAP"
    ROOM_CAPACITY_SUFFICIENT = "ROOM_CAPACITY_SUFFICIENT"
    # Phase 3 (D6): turned OFF for imported data because they compare invented
    # quantities (capacity/strength, 8h/30h caps). A college row re-enables
    # them the day real numbers arrive.
    FACULTY_MAX_HOURS_PER_DAY = "FACULTY_MAX_HOURS_PER_DAY"
    FACULTY_MAX_HOURS_PER_WEEK = "FACULTY_MAX_HOURS_PER_WEEK"
    # OPTIONAL — data-driven, opt-in per profile via config_json (see registry)
    SUBJECT_TIME_PREFERENCE = "SUBJECT_TIME_PREFERENCE"
    MAX_CONSECUTIVE_SAME_TEACHER = "MAX_CONSECUTIVE_SAME_TEACHER"
    MAX_DAILY_SUBJECTS = "MAX_DAILY_SUBJECTS"
    ALLOW_FREE_LAST_SLOT = "ALLOW_FREE_LAST_SLOT"
    TEACHER_YEAR_RESTRICTION = "TEACHER_YEAR_RESTRICTION"
    LAB_BATCH_ROTATION = "LAB_BATCH_ROTATION"
    HOLIDAY_CALENDAR = "HOLIDAY_CALENDAR"
    EXAM_DATE_SEPARATION = "EXAM_DATE_SEPARATION"
    CONTIGUOUS_LAB_SLOTS = "CONTIGUOUS_LAB_SLOTS"
    # Soft
    TEACHER_PREFERS_MORNING = "TEACHER_PREFERS_MORNING"
    AVOID_CONSECUTIVE_SAME_SUBJECT = "AVOID_CONSECUTIVE_SAME_SUBJECT"
    MINIMIZE_STUDENT_FREE_SLOTS = "MINIMIZE_STUDENT_FREE_SLOTS"
    MINIMIZE_TEACHER_FREE_SLOTS = "MINIMIZE_TEACHER_FREE_SLOTS"
    DISTRIBUTE_SUBJECTS_EVENLY = "DISTRIBUTE_SUBJECTS_EVENLY"
    BALANCE_TEACHER_LOAD = "BALANCE_TEACHER_LOAD"
    ROOM_STABILITY = "ROOM_STABILITY"

# The hard/soft split is a catalog concern; keeping it here, next to the enum,
# means ``GET /constraints/types`` and any tooling always reflect exactly what
# the Create schemas accept. Every member must appear in exactly one list.
# assert_registry_enum_parity() additionally requires this list to match the
# validator registry exactly (Phase 3b, A10 — they drifted apart before).
HARD_CONSTRAINT_TYPES = [
    ConstraintType.NO_TEACHER_DOUBLE_BOOK,
    ConstraintType.NO_ROOM_DOUBLE_BOOK,
    ConstraintType.NO_GROUP_DOUBLE_BOOK,
    ConstraintType.NO_CROSS_TIMETABLE_TEACHER_CONFLICT,
    ConstraintType.NO_CROSS_TIMETABLE_ROOM_CONFLICT,
    ConstraintType.NO_CROSS_TIMETABLE_GROUP_CONFLICT,
    ConstraintType.ROOM_REQUIREMENTS_MET,
    ConstraintType.RESPECT_TEACHER_UNAVAILABILITY,
    ConstraintType.RESPECT_ROOM_BLACKOUT,
    ConstraintType.NO_TEACHING_IN_BREAK_SLOT,
    ConstraintType.LAB_ROTATION_COMPLETE,
    ConstraintType.SAME_SUBJECT_SAME_DAY,
    ConstraintType.MAX_ONE_LAB_PER_DAY,
    ConstraintType.CROSS_DEPT_DAILY_CAP,
    ConstraintType.ROOM_CAPACITY_SUFFICIENT,
    ConstraintType.FACULTY_MAX_HOURS_PER_DAY,
    ConstraintType.FACULTY_MAX_HOURS_PER_WEEK,
    ConstraintType.SUBJECT_TIME_PREFERENCE,
    ConstraintType.MAX_CONSECUTIVE_SAME_TEACHER,
    ConstraintType.MAX_DAILY_SUBJECTS,
    ConstraintType.ALLOW_FREE_LAST_SLOT,
    ConstraintType.TEACHER_YEAR_RESTRICTION,
    ConstraintType.LAB_BATCH_ROTATION,
    ConstraintType.HOLIDAY_CALENDAR,
    ConstraintType.EXAM_DATE_SEPARATION,
    ConstraintType.CONTIGUOUS_LAB_SLOTS,
]

SOFT_CONSTRAINT_TYPES = [
    ConstraintType.TEACHER_PREFERS_MORNING,
    ConstraintType.AVOID_CONSECUTIVE_SAME_SUBJECT,
    ConstraintType.MINIMIZE_STUDENT_FREE_SLOTS,
    ConstraintType.MINIMIZE_TEACHER_FREE_SLOTS,
    ConstraintType.DISTRIBUTE_SUBJECTS_EVENLY,
    ConstraintType.BALANCE_TEACHER_LOAD,
    ConstraintType.ROOM_STABILITY,
]

class HardConstraint(Base):
    __tablename__ = "hard_constraints"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_profiles.id"), nullable=True)
    # Plain string (not a DB enum) so new registry rules need no migration.
    constraint_type: Mapped[str] = mapped_column(String(100))
    config_json: Mapped[dict | None] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class SoftConstraint(Base):
    __tablename__ = "soft_constraints"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_profiles.id"), nullable=True)
    constraint_type: Mapped[str] = mapped_column(String(100))
    config_json: Mapped[dict | None] = mapped_column(JSON)
    weight: Mapped[float] = mapped_column(DECIMAL(4, 2), default=1.00)
    description: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
