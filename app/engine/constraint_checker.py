"""Hard-constraint validator for the greedy solver.

Every rule returns a list of :class:`ConstraintViolation`; an empty list
means the candidate slot is acceptable.

All rules — the always-on structural ones and the data-driven profile rules —
are registered validators in ``app.engine.constraint_registry``. The
structural rules (double-booking, capacity, room requirements, availability,
blackouts, faculty load, cross-timetable safety) are dispatched here on every
candidate regardless of the profile's rows; the configured rows are dispatched
after them.
"""
from datetime import time

from sqlalchemy.orm import Session

from app.models.generation import TimetableSlot
from app.models.settings import CollegeSettings
from app.engine.constraint_registry import (
    HARD_CONSTRAINT_REGISTRY,
    STRUCTURAL_RULES,
    ConstraintContext,
)


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
        block_length: int = 1,
        batch_number: int | None = None,
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
        # A block session occupies ``block_length`` consecutive slots starting
        # at ``slot_number`` (1 == a single slot, the historical default).
        self.block_length = block_length
        # Which lab batch this candidate belongs to (1..N). All batches of a
        # parallel practical occupy the same division at the same time in
        # different rooms, so the group double-book rule ignores siblings of
        # the same lab period (they are the same division-wide session).
        self.batch_number = batch_number

    @property
    def slot_numbers(self) -> range:
        """The consecutive slot numbers this candidate occupies."""
        return range(self.slot_number, self.slot_number + self.block_length)


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
        hard_constraints: list | None = None,
        break_slots: set[int] | None = None,
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
        # Data-driven profile constraints dispatched through the registry.
        self.configured = hard_constraints or []
        self.break_slots = set(break_slots or ())
        self.ctx = ConstraintContext(
            db, committed_slots, settings=settings, reserved=self.reserved,
            break_slots=self.break_slots,
        )

    # ── public api ───────────────────────────────────────────
    def check_all(self, candidate: SlotCandidate) -> list[ConstraintViolation]:
        """Run the always-on structural rules, then the configured ones.

        Structural rules are dispatched from the registry in the order of
        ``STRUCTURAL_RULES``; a profile row cannot switch one off. Only after
        them are the profile's data-driven rules run.
        """
        violations: list[ConstraintViolation] = []
        for rule_type in STRUCTURAL_RULES:
            validator = HARD_CONSTRAINT_REGISTRY.get(rule_type)
            if validator is None:
                continue
            reason = validator(candidate, self.committed_slots, None, self.ctx)
            if reason:
                violations.append(ConstraintViolation(rule_type, reason))
        violations += self._check_configured(candidate)
        return violations

    def is_valid(self, candidate: SlotCandidate) -> bool:
        return len(self.check_all(candidate)) == 0

    # ── configured (data-driven) rules ───────────────────────
    def _check_configured(self, c: SlotCandidate) -> list[ConstraintViolation]:
        """Run every profile-configured hard constraint through the registry.

        Each active row's ``constraint_type`` selects a registered validator
        that interprets the row's ``config_json``. Unknown types are ignored
        so an out-of-date deployment degrades gracefully; structural types are
        skipped because they are already always-on (a row of a structural type
        stays decorative).
        """
        violations: list[ConstraintViolation] = []
        for rule in self.configured:
            if not getattr(rule, "is_active", True):
                continue
            rule_type = getattr(rule.constraint_type, "value", rule.constraint_type)
            if rule_type in STRUCTURAL_RULES:
                continue
            validator = HARD_CONSTRAINT_REGISTRY.get(rule_type)
            if validator is None:
                continue
            reason = validator(
                c, self.committed_slots,
                getattr(rule, "config_json", None), self.ctx,
            )
            if reason:
                violations.append(ConstraintViolation(str(rule_type), reason))
        return violations
