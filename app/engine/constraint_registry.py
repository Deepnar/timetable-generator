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


def configured_block_length(subject_id: int, config: dict | None) -> int | None:
    """Resolve how many consecutive slots a subject's lab sessions span.

    config: ``{"block_lengths": {"<subject_id>": int}, "default_block_length"?: int}``
    — a JSON-object key map plus an optional fallback for unlisted subjects.
    A subject explicitly listed in ``block_lengths`` wins over the default;
    ``None`` means the rule does not govern this subject.
    """
    config = config or {}
    lengths = config.get("block_lengths") or {}
    # JSON object keys arrive as strings; accept int or str ids.
    length = lengths.get(str(subject_id))
    if length is None:
        length = lengths.get(subject_id)
    if length is not None:
        return int(length)
    return config.get("default_block_length")


# ── validators ───────────────────────────────────────────────
# Each is intentionally small and pure so new rules are easy to add and test.

def _subject_time_preference(candidate, committed, config, ctx) -> Optional[str]:
    """Force a subject into a slot window.

    config: ``{"subject_id"?: int, "max_slot"?: int, "min_slot"?: int,
               "period"?: "MORNING"|"AFTERNOON", "boundary_slot"?: int}``
    ``period`` is sugar: MORNING => max_slot=boundary, AFTERNOON => min_slot=boundary+1.
    Omitting ``subject_id`` applies the rule to every subject. A multi-slot
    block must fit entirely inside the window (its last slot bounded by
    ``max_slot``, its first by ``min_slot``).
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

    start = candidate.slot_number
    end = candidate.slot_number + candidate.block_length - 1
    if max_slot is not None and end > max_slot:
        return (
            f"subject {candidate.subject_id} must end at/before slot "
            f"{max_slot} (block ends at {end})"
        )
    if min_slot is not None and start < min_slot:
        return (
            f"subject {candidate.subject_id} must start at/after slot "
            f"{min_slot} (block starts at {start})"
        )
    return None


def _max_consecutive_same_teacher(candidate, committed, config, ctx) -> Optional[str]:
    """Cap a teacher's back-to-back slots on a single day.

    config: ``{"max": int, "faculty_id"?: int}``. Without ``faculty_id`` the
    cap applies to every teacher. A multi-slot block counts as one contiguous
    run, so a 3-slot lab block advances the run by 3.
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
    occupied = set(candidate.slot_numbers)
    same_day |= occupied

    run = len(occupied)
    left = candidate.slot_number - 1
    while left in same_day:
        run += 1
        left -= 1
    right = candidate.slot_number + candidate.block_length
    while right in same_day:
        run += 1
        right += 1

    if run > max_run:
        return (
            f"faculty {candidate.faculty_id} would exceed {max_run} consecutive "
            f"slots on day {candidate.day_of_week}"
        )
    return None


def _lab_batch_rotation(candidate, committed, config, ctx) -> Optional[str]:
    """Pin a group's (lab batch's) sessions to specific weekdays.

    config: ``{"group_days": {"<group_id>": [day_of_week, ...]}}`` — e.g.
    ``{"group_days": {"11": [0], "12": [1]}}`` puts batch A1 on Monday and A2
    on Tuesday. Groups not listed are unrestricted.
    """
    config = config or {}
    group_days = config.get("group_days") or {}
    # JSON object keys are strings; accept int or str group ids.
    allowed = group_days.get(str(candidate.student_group_id))
    if allowed is None:
        allowed = group_days.get(candidate.student_group_id)
    if not allowed:
        return None
    if candidate.day_of_week not in allowed:
        return (
            f"group {candidate.student_group_id} may only run on weekdays "
            f"{allowed} (got {candidate.day_of_week})"
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


def _holiday_calendar(candidate, committed, config, ctx) -> Optional[str]:
    """Refuse placements on configured holiday dates.

    config: ``{"holidays": ["YYYY-MM-DD", ...]}`` — a list of ISO date
    strings. A candidate whose materialized ``slot_date`` (derived from
    ``day_of_week`` relative to the profile's ``term_start``) falls on a
    listed holiday is rejected; a candidate carrying no materialized date
    (no ``term_start`` anchor) is a no-op, mirroring the availability-window
    rule for date-bounded rows.
    """
    config = config or {}
    holidays = config.get("holidays") or []
    if not holidays or candidate.slot_date is None:
        return None
    key = candidate.slot_date.isoformat()
    if key in holidays:
        return f"{key} is a holiday; no sessions scheduled"
    return None


def _exam_date_separation(candidate, committed, config, ctx) -> Optional[str]:
    """Require a minimum number of days between a group's exams.

    config: ``{"min_days": int, "group_id"?: int}``. Only applies to ``EXAM``
    sessions that carry a materialized ``slot_date`` (derived from
    ``day_of_week`` relative to the profile's ``term_start``); a candidate with
    no date is a no-op, mirroring ``HOLIDAY_CALENDAR``. Two exams for the same
    group closer than ``min_days`` calendar days apart are rejected, which
    keeps one branch/year's exams spaced out while other branches run normal
    classes.
    """
    config = config or {}
    min_days = config.get("min_days")
    if not min_days:
        return None
    group_id = config.get("group_id")
    if group_id is not None and candidate.student_group_id != group_id:
        return None
    if candidate.session_type != "EXAM" or candidate.slot_date is None:
        return None
    for s in committed:
        if (
            s.session_type != "EXAM"
            or s.student_group_id != candidate.student_group_id
        ):
            continue
        if s.slot_date is None:
            continue
        gap = abs((candidate.slot_date - s.slot_date).days)
        if gap < min_days:
            return (
                f"group {candidate.student_group_id} exams must be at least "
                f"{min_days} days apart ({candidate.slot_date.isoformat()} is "
                f"{gap} day(s) from {s.slot_date.isoformat()})"
            )
    return None


def _contiguous_lab_slots(candidate, committed, config, ctx) -> Optional[str]:
    """Require lab blocks to span exactly the configured number of slots.

    config: ``{"block_lengths": {"<subject_id>": int}, "default_block_length"?: int}``
    — how many consecutive slots each lab session of a subject occupies. The
    solver expands a lab subject's ``weekly_hours`` into blocks of that size
    (any remainder stays single-slot), so this validator is a consistency
    guard: a block candidate must match the size configured for its subject,
    and candidates of subjects the rule does not explicitly list are untouched.
    """
    config = config or {}
    # Only explicitly-listed subjects are checked; ``default_block_length`` is
    # a fallback for the solver's expansion and does not govern validation here
    # (the solver always forms default-sized blocks anyway).
    lengths = config.get("block_lengths") or {}
    expected = lengths.get(str(candidate.subject_id))
    if expected is None:
        expected = lengths.get(candidate.subject_id)
    if expected is None or candidate.block_length <= 1:
        return None
    if candidate.block_length != int(expected):
        return (
            f"subject {candidate.subject_id} lab sessions must run as "
            f"{expected} contiguous slots (got {candidate.block_length})"
        )
    return None


# Register after definition so the functions read top-to-bottom.
hard_rule("SUBJECT_TIME_PREFERENCE")(_subject_time_preference)
hard_rule("MAX_CONSECUTIVE_SAME_TEACHER")(_max_consecutive_same_teacher)
hard_rule("TEACHER_YEAR_RESTRICTION")(_teacher_year_restriction)
hard_rule("LAB_BATCH_ROTATION")(_lab_batch_rotation)
hard_rule("HOLIDAY_CALENDAR")(_holiday_calendar)
hard_rule("EXAM_DATE_SEPARATION")(_exam_date_separation)
hard_rule("CONTIGUOUS_LAB_SLOTS")(_contiguous_lab_slots)
