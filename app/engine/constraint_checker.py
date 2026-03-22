from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import time
from app.models.generation import TimetableSlot
from app.models.rooms import Room, RoomType
from app.models.faculty import FacultyAvailability, AvailabilityType
from app.models.rooms import RoomBlackout
from app.models.subjects import Subject


class SlotCandidate:
    """
    Represents one possible assignment the solver is considering.
    Before committing, this gets validated by the constraint checker.
    """
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
        slot_date=None
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


class ConstraintViolation:
    """Describes why a slot candidate failed validation."""
    def __init__(self, constraint: str, reason: str):
        self.constraint = constraint
        self.reason = reason

    def __repr__(self):
        return f"{self.constraint}: {self.reason}"


class ConstraintChecker:
    """
    Validates a SlotCandidate against all hard constraints.
    Returns a list of violations — empty list means the slot is valid.
    """

    def __init__(self, db: Session, committed_slots: list[TimetableSlot]):
        self.db = db
        # These are already assigned slots in the current generation run
        # Used to check double-booking
        self.committed_slots = committed_slots

    def check_all(self, candidate: SlotCandidate) -> list[ConstraintViolation]:
        violations = []

        violations += self._check_teacher_double_book(candidate)
        violations += self._check_room_double_book(candidate)
        violations += self._check_group_double_book(candidate)
        violations += self._check_room_capacity(candidate)
        violations += self._check_room_type_match(candidate)
        violations += self._check_teacher_availability(candidate)
        violations += self._check_room_blackout(candidate)

        return violations

    def is_valid(self, candidate: SlotCandidate) -> bool:
        return len(self.check_all(candidate)) == 0

    # ── Individual constraint checks ─────────────────────────

    def _check_teacher_double_book(
        self, candidate: SlotCandidate
    ) -> list[ConstraintViolation]:
        """Teacher cannot be in two places at the same time."""
        for slot in self.committed_slots:
            if (
                slot.faculty_id == candidate.faculty_id
                and slot.day_of_week == candidate.day_of_week
                and slot.slot_number == candidate.slot_number
            ):
                return [ConstraintViolation(
                    "NO_TEACHER_DOUBLE_BOOK",
                    f"Faculty {candidate.faculty_id} already assigned "
                    f"day {candidate.day_of_week} slot {candidate.slot_number}"
                )]
        return []

    def _check_room_double_book(
        self, candidate: SlotCandidate
    ) -> list[ConstraintViolation]:
        """Room cannot host two sessions simultaneously."""
        for slot in self.committed_slots:
            if (
                slot.room_id == candidate.room_id
                and slot.day_of_week == candidate.day_of_week
                and slot.slot_number == candidate.slot_number
            ):
                return [ConstraintViolation(
                    "NO_ROOM_DOUBLE_BOOK",
                    f"Room {candidate.room_id} already booked "
                    f"day {candidate.day_of_week} slot {candidate.slot_number}"
                )]
        return []

    def _check_group_double_book(
        self, candidate: SlotCandidate
    ) -> list[ConstraintViolation]:
        """Student group cannot attend two sessions at once."""
        for slot in self.committed_slots:
            if (
                slot.student_group_id == candidate.student_group_id
                and slot.day_of_week == candidate.day_of_week
                and slot.slot_number == candidate.slot_number
            ):
                return [ConstraintViolation(
                    "NO_GROUP_DOUBLE_BOOK",
                    f"Group {candidate.student_group_id} already scheduled "
                    f"day {candidate.day_of_week} slot {candidate.slot_number}"
                )]
        return []

    def _check_room_capacity(
        self, candidate: SlotCandidate
    ) -> list[ConstraintViolation]:
        """Room capacity must be enough for the student group."""
        from app.models.groups import StudentGroup
        room = self.db.scalars(
            select(Room).where(Room.id == candidate.room_id)
        ).first()
        group = self.db.scalars(
            select(StudentGroup).where(
                StudentGroup.id == candidate.student_group_id)
        ).first()
        if room and group and room.capacity < group.strength:
            return [ConstraintViolation(
                "ROOM_CAPACITY_SUFFICIENT",
                f"Room {room.name} capacity {room.capacity} "
                f"< group strength {group.strength}"
            )]
        return []

    def _check_room_type_match(
        self, candidate: SlotCandidate
    ) -> list[ConstraintViolation]:
        """Lab subjects must be assigned to lab rooms."""
        subject = self.db.scalars(
            select(Subject).where(Subject.id == candidate.subject_id)
        ).first()
        room = self.db.scalars(
            select(Room).where(Room.id == candidate.room_id)
        ).first()
        if subject and room:
            if subject.requires_lab and room.room_type != RoomType.LAB:
                return [ConstraintViolation(
                    "ROOM_TYPE_MATCH",
                    f"Subject {subject.name} requires lab "
                    f"but room {room.name} is {room.room_type}"
                )]
        return []

    def _check_teacher_availability(
        self, candidate: SlotCandidate
    ) -> list[ConstraintViolation]:
        """Respect teacher unavailability windows."""
        unavailable_windows = self.db.scalars(
            select(FacultyAvailability).where(
                FacultyAvailability.faculty_id == candidate.faculty_id,
                FacultyAvailability.day_of_week == candidate.day_of_week,
                FacultyAvailability.availability == AvailabilityType.UNAVAILABLE
            )
        ).all()
        for window in unavailable_windows:
            if window.slot_start and window.slot_end:
                # check if candidate slot overlaps with unavailability window
                if (
                    candidate.start_time < window.slot_end
                    and candidate.end_time > window.slot_start
                ):
                    return [ConstraintViolation(
                        "RESPECT_TEACHER_UNAVAILABILITY",
                        f"Faculty {candidate.faculty_id} unavailable "
                        f"day {candidate.day_of_week} "
                        f"{window.slot_start}-{window.slot_end}"
                    )]
            else:
                # full day unavailability
                return [ConstraintViolation(
                    "RESPECT_TEACHER_UNAVAILABILITY",
                    f"Faculty {candidate.faculty_id} unavailable "
                    f"all day on day {candidate.day_of_week}"
                )]
        return []

    def _check_room_blackout(
        self, candidate: SlotCandidate
    ) -> list[ConstraintViolation]:
        """Respect room blackout windows."""
        if not candidate.slot_date:
            return []
        blackouts = self.db.scalars(
            select(RoomBlackout).where(
                RoomBlackout.room_id == candidate.room_id,
                RoomBlackout.date == candidate.slot_date
            )
        ).all()
        for blackout in blackouts:
            if blackout.slot_start and blackout.slot_end:
                if (
                    candidate.start_time < blackout.slot_end
                    and candidate.end_time > blackout.slot_start
                ):
                    return [ConstraintViolation(
                        "RESPECT_ROOM_BLACKOUT",
                        f"Room {candidate.room_id} blacked out "
                        f"{blackout.slot_start}-{blackout.slot_end} "
                        f"on {candidate.slot_date}"
                    )]
            else:
                return [ConstraintViolation(
                    "RESPECT_ROOM_BLACKOUT",
                    f"Room {candidate.room_id} blacked out "
                    f"all day on {candidate.slot_date}"
                )]
        return []