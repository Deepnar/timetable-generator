"""Dynamic hard-constraint registry.

Maps a constraint *type* (string) to a validator function so a new rule can be
added by writing one function and registering it — no changes to the solver,
the constraint checker, or the DB schema. Profile-scoped ``hard_constraints``
rows carry a ``config_json`` blob that the matching validator interprets.

A validator has the signature::

    (candidate, committed_slots, config, ctx) -> str | None

and returns a human-readable reason on violation, or ``None`` when the
candidate is acceptable. ``ctx`` is a :class:`ConstraintContext` providing
cached lookups so validators don't each re-query the database.
"""
from __future__ import annotations

from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.models.groups import StudentGroup

# type string -> validator
HARD_CONSTRAINT_REGISTRY: dict[str, Callable] = {}


def hard_rule(constraint_type) -> Callable:
    """Register a validator for a constraint type (enum member or string)."""
    key = getattr(constraint_type, "value", constraint_type)

    def deco(fn: Callable) -> Callable:
        HARD_CONSTRAINT_REGISTRY[key] = fn
        return fn

    return deco


class ConstraintContext:
    """Shared, cached lookups handed to every validator."""

    def __init__(self, db: Session, committed_slots: list):
        self.db = db
        self.committed_slots = committed_slots
        self._group_cache: dict[int, Optional[StudentGroup]] = {}

    def group(self, group_id: int) -> Optional[StudentGroup]:
        if group_id not in self._group_cache:
            self._group_cache[group_id] = self.db.get(StudentGroup, group_id)
        return self._group_cache[group_id]


# ── validators ───────────────────────────────────────────────
# Each is intentionally small and pure so new rules are easy to add and test.

def _subject_time_preference(candidate, committed, config, ctx) -> Optional[str]:
    """Force a subject into a slot window.

    config: ``{"subject_id"?: int, "max_slot"?: int, "min_slot"?: int,
               "period"?: "MORNING"|"AFTERNOON", "boundary_slot"?: int}``
    ``period`` is sugar: MORNING => max_slot=boundary, AFTERNOON => min_slot=boundary+1.
    Omitting ``subject_id`` applies the rule to every subject.
    """
    config = config or {}
    subject_id = config.get("subject_id")
    if subject_id is not None and candidate.subject_id != subject_id:
        return None

    max_slot = config.get("max_slot")
    min_slot = config.get("min_slot")
    period = config.get("period")
    boundary = config.get("boundary_slot")
    if period == "MORNING" and boundary is not None and max_slot is None:
        max_slot = boundary
    if period == "AFTERNOON" and boundary is not None and min_slot is None:
        min_slot = boundary + 1

    slot = candidate.slot_number
    if max_slot is not None and slot > max_slot:
        return f"subject {candidate.subject_id} must be at/before slot {max_slot} (got {slot})"
    if min_slot is not None and slot < min_slot:
        return f"subject {candidate.subject_id} must be at/after slot {min_slot} (got {slot})"
    return None


def _max_consecutive_same_teacher(candidate, committed, config, ctx) -> Optional[str]:
    """Cap a teacher's back-to-back slots on a single day.

    config: ``{"max": int, "faculty_id"?: int}``. Without ``faculty_id`` the
    cap applies to every teacher.
    """
    config = config or {}
    max_run = config.get("max")
    if not max_run:
        return None
    faculty_id = config.get("faculty_id")
    if faculty_id is not None and candidate.faculty_id != faculty_id:
        return None

    same_day = {
        s.slot_number
        for s in committed
        if s.faculty_id == candidate.faculty_id
        and s.day_of_week == candidate.day_of_week
    }
    same_day.add(candidate.slot_number)

    run = 1
    left = candidate.slot_number - 1
    while left in same_day:
        run += 1
        left -= 1
    right = candidate.slot_number + 1
    while right in same_day:
        run += 1
        right += 1

    if run > max_run:
        return (
            f"faculty {candidate.faculty_id} would exceed {max_run} consecutive "
            f"slots on day {candidate.day_of_week}"
        )
    return None


def _teacher_year_restriction(candidate, committed, config, ctx) -> Optional[str]:
    """Restrict a teacher to specific student years.

    config: ``{"faculty_id": int, "allowed_years": [int, ...]}``.
    """
    config = config or {}
    faculty_id = config.get("faculty_id")
    allowed = config.get("allowed_years")
    if faculty_id is None or not allowed:
        return None
    if candidate.faculty_id != faculty_id:
        return None
    group = ctx.group(candidate.student_group_id) if ctx else None
    if group is None or group.year is None:
        return None
    if group.year not in allowed:
        return f"faculty {faculty_id} may not teach year {group.year} (allowed {allowed})"
    return None


# Register after definition so the functions read top-to-bottom.
hard_rule("SUBJECT_TIME_PREFERENCE")(_subject_time_preference)
hard_rule("MAX_CONSECUTIVE_SAME_TEACHER")(_max_consecutive_same_teacher)
hard_rule("TEACHER_YEAR_RESTRICTION")(_teacher_year_restriction)
