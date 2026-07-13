"""Hard-constraint validator for the greedy solver.

Every rule returns a list of :class:`ConstraintViolation`; an empty list
means the candidate slot is acceptable.
"""
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import time

from app.models.generation import TimetableSlot
from app.models.rooms import Room, RoomType, RoomBlackout
from app.models.faculty import Faculty, FacultyAvailability, AvailabilityType
from app.models.subjects import Subject
from app.models.groups import StudentGroup
from app.models.settings import CollegeSettings


class SlotCandidate:
    """A potential placement the solver is considering."""

    def __init__(
        self,
        instance_id: int,
        day_of_week: int,
        slot_number: int,
        start_time: time,
        end_time: time,
        faculty_id: int,
        room_id: int,
        student_group_id: int,
        subject_id: int,
        session_type: str,
        slot_date=None,
        is_cross_department: bool = False,
    ):
        self.instance_id = instance_id
        self.day_of_week = day_of_week
        self.slot_number = slot_number
        self.start_time = start_time
        self.end_time = end_time
        self.faculty_id = faculty_id
        self.room_id = room_id
        self.student_group_id = student_group_id
        self.subject_id = subject_id
        self.session_type = session_type
        self.slot_date = slot_date
        self.is_cross_department = is_cross_department


class ConstraintViolation:
    """Describes why a candidate failed validation."""

    def __init__(self, constraint: str, reason: str):
        self.constraint = constraint
        self.reason = reason

    def __repr__(self) -> str:
        return f"{self.constraint}: {self.reason}"


class ConstraintChecker:
    """Validates a :class:`SlotCandidate` against all hard rules."""

    def __init__(
        self,
        db: Session,
        committed_slots: list[TimetableSlot],
        settings: CollegeSettings | None = None,
        reserved: dict[str, set[tuple]] | None = None,
    ):
        self.db = db
        self.committed_slots = committed_slots
        # settings is optional so the checker is still usable in tests
        # that only care about core constraints.
        self.settings = settings
        # ``reserved`` holds resource-level (id, day, slot) tuples that are
        # already taken by PUBLISHED timetables from *other* generation runs.
        # Split per resource so a published booking blocks the faculty, room,
        # or group at that time slot regardless of the other two dimensions.
        self.reserved = reserved or {}

    # ── public api ───────────────────────────────────────────
    def check_all(self, candidate: SlotCandidate) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []
        violations += self._check_teacher_double_book(candidate)
        violations += self._check_room_double_book(candidate)
        violations += self._check_group_double_book(candidate)
        violations += self._check_published_conflicts(candidate)
        violations += self._check_room_capacity(candidate)
        violations += self._check_room_type_match(candidate)
        violations += self._check_teacher_availability(candidate)
        violations += self._check_faculty_load(candidate)
        violations += self._check_room_blackout(candidate)
        violations += self._check_same_subject_same_day(candidate)
        violations += self._check_cross_dept_cap(candidate)
        return violations

    def is_valid(self, candidate: SlotCandidate) -> bool:
        return len(self.check_all(candidate)) == 0

    # ── individual checks ────────────────────────────────────
    def _check_teacher_double_book(self, c: SlotCandidate) -> list[ConstraintViolation]:
        for s in self.committed_slots:
            if (
                s.faculty_id == c.faculty_id
                and s.day_of_week == c.day_of_week
                and s.slot_number == c.slot_number
            ):
                return [ConstraintViolation(
                    "NO_TEACHER_DOUBLE_BOOK",
                    f"Faculty {c.faculty_id} already assigned "
                    f"day {c.day_of_week} slot {c.slot_number}",
                )]
        return []

    def _check_room_double_book(self, c: SlotCandidate) -> list[ConstraintViolation]:
        for s in self.committed_slots:
            if (
                s.room_id == c.room_id
                and s.day_of_week == c.day_of_week
                and s.slot_number == c.slot_number
            ):
                return [ConstraintViolation(
                    "NO_ROOM_DOUBLE_BOOK",
                    f"Room {c.room_id} already booked "
                    f"day {c.day_of_week} slot {c.slot_number}",
                )]
        return []

    def _check_group_double_book(self, c: SlotCandidate) -> list[ConstraintViolation]:
        for s in self.committed_slots:
            if (
                s.student_group_id == c.student_group_id
                and s.day_of_week == c.day_of_week
                and s.slot_number == c.slot_number
            ):
                return [ConstraintViolation(
                    "NO_GROUP_DOUBLE_BOOK",
                    f"Group {c.student_group_id} already scheduled "
                    f"day {c.day_of_week} slot {c.slot_number}",
                )]
        return []

    def _check_published_conflicts(self, c: SlotCandidate) -> list[ConstraintViolation]:
        """Reject placements that collide with an already-PUBLISHED timetable.

        Cross-timetable safety: a teacher, room, or group booked at
        (day, slot) in any published instance cannot be reused here, even if
        the other two dimensions differ.
        """
        if not self.reserved:
            return []
        key = (c.day_of_week, c.slot_number)
        if (c.faculty_id, *key) in self.reserved.get("faculty", ()):
            return [ConstraintViolation(
                "NO_CROSS_TIMETABLE_TEACHER_CONFLICT",
                f"Faculty {c.faculty_id} already booked in a published "
                f"timetable on day {c.day_of_week} slot {c.slot_number}",
            )]
        if (c.room_id, *key) in self.reserved.get("room", ()):
            return [ConstraintViolation(
                "NO_CROSS_TIMETABLE_ROOM_CONFLICT",
                f"Room {c.room_id} already booked in a published "
                f"timetable on day {c.day_of_week} slot {c.slot_number}",
            )]
        if (c.student_group_id, *key) in self.reserved.get("group", ()):
            return [ConstraintViolation(
                "NO_CROSS_TIMETABLE_GROUP_CONFLICT",
                f"Group {c.student_group_id} already scheduled in a published "
                f"timetable on day {c.day_of_week} slot {c.slot_number}",
            )]
        return []

    def _check_room_capacity(self, c: SlotCandidate) -> list[ConstraintViolation]:
        room = self.db.scalars(select(Room).where(Room.id == c.room_id)).first()
        group = self.db.scalars(
            select(StudentGroup).where(StudentGroup.id == c.student_group_id)
        ).first()
        if room and group and room.capacity < group.strength:
            return [ConstraintViolation(
                "ROOM_CAPACITY_SUFFICIENT",
                f"Room {room.name} capacity {room.capacity} "
                f"< group strength {group.strength}",
            )]
        return []

    def _check_room_type_match(self, c: SlotCandidate) -> list[ConstraintViolation]:
        subject = self.db.scalars(
            select(Subject).where(Subject.id == c.subject_id)
        ).first()
        room = self.db.scalars(select(Room).where(Room.id == c.room_id)).first()
        if subject and room and subject.requires_lab and room.room_type != RoomType.LAB:
            return [ConstraintViolation(
                "ROOM_TYPE_MATCH",
                f"Subject {subject.name} requires lab but room {room.name} "
                f"is {room.room_type}",
            )]
        return []

    def _check_teacher_availability(self, c: SlotCandidate) -> list[ConstraintViolation]:
        windows = self.db.scalars(
            select(FacultyAvailability).where(
                FacultyAvailability.faculty_id == c.faculty_id,
                FacultyAvailability.day_of_week == c.day_of_week,
                FacultyAvailability.availability == AvailabilityType.UNAVAILABLE,
            )
        ).all()
        for w in windows:
            if w.slot_start and w.slot_end:
                if c.start_time < w.slot_end and c.end_time > w.slot_start:
                    return [ConstraintViolation(
                        "RESPECT_TEACHER_UNAVAILABILITY",
                        f"Faculty {c.faculty_id} unavailable "
                        f"day {c.day_of_week} {w.slot_start}-{w.slot_end}",
                    )]
            else:
                return [ConstraintViolation(
                    "RESPECT_TEACHER_UNAVAILABILITY",
                    f"Faculty {c.faculty_id} unavailable all day {c.day_of_week}",
                )]
        return []

    def _check_faculty_load(self, c: SlotCandidate) -> list[ConstraintViolation]:
        """Enforce a teacher's ``max_hours_per_day`` / ``max_hours_per_week``.

        One slot counts as one hour (the domain uses "hours" and "slots"
        interchangeably). A ``0``/falsy limit means "no limit".
        """
        faculty = self.db.get(Faculty, c.faculty_id)
        if not faculty:
            return []
        if faculty.max_hours_per_day:
            day_count = sum(
                1
                for s in self.committed_slots
                if s.faculty_id == c.faculty_id and s.day_of_week == c.day_of_week
            )
            if day_count >= faculty.max_hours_per_day:
                return [ConstraintViolation(
                    "FACULTY_MAX_HOURS_PER_DAY",
                    f"Faculty {c.faculty_id} already at daily cap "
                    f"{faculty.max_hours_per_day} on day {c.day_of_week}",
                )]
        if faculty.max_hours_per_week:
            week_count = sum(
                1 for s in self.committed_slots if s.faculty_id == c.faculty_id
            )
            if week_count >= faculty.max_hours_per_week:
                return [ConstraintViolation(
                    "FACULTY_MAX_HOURS_PER_WEEK",
                    f"Faculty {c.faculty_id} already at weekly cap "
                    f"{faculty.max_hours_per_week}",
                )]
        return []

    def _check_room_blackout(self, c: SlotCandidate) -> list[ConstraintViolation]:
        if not c.slot_date:
            return []
        blackouts = self.db.scalars(
            select(RoomBlackout).where(
                RoomBlackout.room_id == c.room_id,
                RoomBlackout.date == c.slot_date,
            )
        ).all()
        for b in blackouts:
            if b.slot_start and b.slot_end:
                if c.start_time < b.slot_end and c.end_time > b.slot_start:
                    return [ConstraintViolation(
                        "RESPECT_ROOM_BLACKOUT",
                        f"Room {c.room_id} blacked out "
                        f"{b.slot_start}-{b.slot_end} on {c.slot_date}",
                    )]
            else:
                return [ConstraintViolation(
                    "RESPECT_ROOM_BLACKOUT",
                    f"Room {c.room_id} blacked out all day on {c.slot_date}",
                )]
        return []

    def _check_same_subject_same_day(self, c: SlotCandidate) -> list[ConstraintViolation]:
        for s in self.committed_slots:
            if (
                s.subject_id == c.subject_id
                and s.student_group_id == c.student_group_id
                and s.day_of_week == c.day_of_week
            ):
                return [ConstraintViolation(
                    "SAME_SUBJECT_SAME_DAY",
                    f"Subject {c.subject_id} already scheduled for group "
                    f"{c.student_group_id} on day {c.day_of_week}",
                )]
        return []

    def _check_cross_dept_cap(self, c: SlotCandidate) -> list[ConstraintViolation]:
        """Optional hard rule driven by college feature flag.

        If the college has ``max_cross_dept_per_day`` configured in its
        ``config_json`` blob, refuse the placement when the same faculty
        would teach a cross-department group more than N times on this day.
        """
        if not self.settings or not c.is_cross_department:
            return []
        cap = (self.settings.config_json or {}).get("max_cross_dept_per_day")
        if cap is None:
            return []
        count = sum(
            1
            for s in self.committed_slots
            if s.faculty_id == c.faculty_id
            and s.day_of_week == c.day_of_week
        )
        if count >= int(cap):
            return [ConstraintViolation(
                "CROSS_DEPT_DAILY_CAP",
                f"Faculty {c.faculty_id} already teaches {count} cross-dept "
                f"sessions on day {c.day_of_week} (cap {cap})",
            )]
        return []
