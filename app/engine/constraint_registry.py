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

Every rule — including the core structural ones (double-booking, capacity,
room requirements, availability, blackouts, faculty load, cross-timetable
safety) — lives in this registry. The structural rules are *always-on*: the
:class:`ConstraintChecker` dispatches the :data:`STRUCTURAL_RULES` list on
every candidate, independent of any ``hard_constraints`` row, so they can
never be turned off by data. Data-driven rules (``SUBJECT_TIME_PREFERENCE``
etc.) are dispatched only when a profile row asks for them.
"""
from __future__ import annotations

from typing import Callable, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.groups import StudentGroup
from app.models.rooms import Room, RoomBlackout
from app.models.subjects import Subject
from app.models.faculty import Faculty, FacultyAvailability, AvailabilityType

# type string -> validator
HARD_CONSTRAINT_REGISTRY: dict[str, Callable] = {}

# The always-on structural rules, in the order the checker reports them.
# They are dispatched by :meth:`ConstraintChecker.check_all` on every candidate
# regardless of the profile's ``hard_constraints`` rows; rows of these types
# stay decorative (a profile cannot switch a structural rule off).
STRUCTURAL_RULES: tuple[str, ...] = (
    "NO_TEACHER_DOUBLE_BOOK",
    "NO_ROOM_DOUBLE_BOOK",
    "NO_GROUP_DOUBLE_BOOK",
    "NO_CROSS_TIMETABLE_TEACHER_CONFLICT",
    "NO_CROSS_TIMETABLE_ROOM_CONFLICT",
    "NO_CROSS_TIMETABLE_GROUP_CONFLICT",
    "ROOM_CAPACITY_SUFFICIENT",
    "ROOM_REQUIREMENTS_MET",
    "RESPECT_TEACHER_UNAVAILABILITY",
    "FACULTY_MAX_HOURS_PER_DAY",
    "FACULTY_MAX_HOURS_PER_WEEK",
    "RESPECT_ROOM_BLACKOUT",
    "SAME_SUBJECT_SAME_DAY",
    "CROSS_DEPT_DAILY_CAP",
)


def hard_rule(constraint_type) -> Callable:
    """Register a validator for a constraint type (enum member or string)."""
    key = getattr(constraint_type, "value", constraint_type)

    def deco(fn: Callable) -> Callable:
        HARD_CONSTRAINT_REGISTRY[key] = fn
        return fn

    return deco


class ConstraintContext:
    """Shared, cached lookups handed to every validator.

    ``settings`` and ``reserved`` are the college feature-flag singleton and
    the per-resource cross-timetable reservations; structural validators read
    them from here instead of threading extra arguments through the registry
    signature. The lookup caches are keyed by id and are safe to reuse across
    a whole solve because the referenced rows never change mid-run.
    """

    def __init__(
        self,
        db: Session,
        committed_slots: list,
        settings=None,
        reserved: dict[str, set[tuple]] | None = None,
    ):
        self.db = db
        self.committed_slots = committed_slots
        self.settings = settings
        self.reserved = reserved or {}
        self._group_cache: dict[int, Optional[StudentGroup]] = {}
        self._subject_cache: dict[int, Optional[Subject]] = {}
        self._room_cache: dict[int, Optional[Room]] = {}
        self._faculty_cache: dict[int, Optional[Faculty]] = {}
        self._unavailability_cache: dict[int, list] = {}
        self._blackout_cache: dict[int, list] = {}

    def group(self, group_id: int) -> Optional[StudentGroup]:
        if group_id not in self._group_cache:
            self._group_cache[group_id] = self.db.get(StudentGroup, group_id)
        return self._group_cache[group_id]

    def subject(self, subject_id: int) -> Optional[Subject]:
        if subject_id not in self._subject_cache:
            self._subject_cache[subject_id] = self.db.get(Subject, subject_id)
        return self._subject_cache[subject_id]

    def room(self, room_id: int) -> Optional[Room]:
        if room_id not in self._room_cache:
            self._room_cache[room_id] = self.db.get(Room, room_id)
        return self._room_cache[room_id]

    def faculty(self, faculty_id: int) -> Optional[Faculty]:
        if faculty_id not in self._faculty_cache:
            self._faculty_cache[faculty_id] = self.db.get(Faculty, faculty_id)
        return self._faculty_cache[faculty_id]

    def unavailability(self, faculty_id: int) -> list[FacultyAvailability]:
        """All UNAVAILABLE rows for a faculty member (uncached per id)."""
        if faculty_id not in self._unavailability_cache:
            rows = self.db.scalars(
                select(FacultyAvailability).where(
                    FacultyAvailability.faculty_id == faculty_id,
                    FacultyAvailability.availability == AvailabilityType.UNAVAILABLE,
                )
            ).all()
            self._unavailability_cache[faculty_id] = rows
        return self._unavailability_cache[faculty_id]

    def blackouts(self, room_id: int) -> list[RoomBlackout]:
        if room_id not in self._blackout_cache:
            rows = self.db.scalars(
                select(RoomBlackout).where(RoomBlackout.room_id == room_id)
            ).all()
            self._blackout_cache[room_id] = rows
        return self._blackout_cache[room_id]


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


@hard_rule("MAX_DAILY_SUBJECTS")
def _max_daily_subjects(candidate, committed, config, ctx) -> Optional[str]:
    """Cap how many distinct subjects a group can sit in a single day.

    config: ``{"max": int, "group_id"?: int, "subject_id"?: int}``. Without
    ``group_id`` the cap applies to every group; ``subject_id`` narrows the
    rule to one subject. A common real-world rule ("don't give a class five
    different subjects in one day") that the base engine leaves unlimited.
    """
    config = config or {}
    max_subjects = config.get("max")
    if not max_subjects:
        return None
    group_id = config.get("group_id")
    subject_id = config.get("subject_id")
    if group_id is not None and candidate.student_group_id != group_id:
        return None
    if subject_id is not None and candidate.subject_id != subject_id:
        return None
    if candidate.student_group_id is None or candidate.day_of_week is None:
        return None

    distinct = {
        s.subject_id
        for s in committed
        if s.student_group_id == candidate.student_group_id
        and s.day_of_week == candidate.day_of_week
        and s.subject_id is not None
    }
    distinct.add(candidate.subject_id)
    if len(distinct) > max_subjects:
        return (
            f"group {candidate.student_group_id} would have {len(distinct)} "
            f"distinct subjects on day {candidate.day_of_week} "
            f"(cap {max_subjects})"
        )
    return None


def _lab_batch_rotation(candidate, committed, config, ctx) -> Optional[str]:
    """Pin a group's (lab batch's) sessions to specific weekdays.

    config: ``{"group_days": {"<group_id>": [day_of_week, ...]}}`` — e.g.
    ``{"group_days": {"11": [0], "12": [1]}}`` puts batch A1 on Monday and A2
    on Tuesday. Groups not listed are unrestricted.

    Gated by the college ``enable_lab_batches`` feature flag: with it off
    (the default) the rule is inert, so lab-batch rotation is opt-in.
    """
    # ``ctx`` is None in unit tests, which keep the rule active.
    if ctx is not None and ctx.settings is not None:
        if not ctx.settings.enable_lab_batches:
            return None
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


# ── structural (always-on) validators ─────────────────────────
# The non-negotiable checks that used to live inline in ConstraintChecker.
# They are registered here so every rule is a validator; the checker runs them
# via STRUCTURAL_RULES on every candidate, so no profile row can switch one
# off (a row of a structural type stays decorative).

def _availability_window_applies(w, slot_date) -> bool:
    """Whether an availability row is active for a candidate slot.

    A window with no date bounds is timeless and always applies. One with
    ``effective_from``/``effective_to`` only applies when the slot's
    materialized calendar date falls inside them (inclusive; a missing bound
    means "unbounded" on that side). Without a materialized date there is
    nothing to compare, so a date-bounded window is treated as inert — the
    same rule that governs date-specific room blackouts.
    """
    if w.effective_from is None and w.effective_to is None:
        return True
    if slot_date is None:
        return False
    if w.effective_from is not None and slot_date < w.effective_from:
        return False
    if w.effective_to is not None and slot_date > w.effective_to:
        return False
    return True


@hard_rule("NO_TEACHER_DOUBLE_BOOK")
def _no_teacher_double_book(candidate, committed, config, ctx) -> Optional[str]:
    for s in committed:
        if (
            s.faculty_id == candidate.faculty_id
            and s.day_of_week == candidate.day_of_week
            and s.slot_number in candidate.slot_numbers
        ):
            return (
                f"faculty {candidate.faculty_id} already assigned "
                f"day {candidate.day_of_week} slot {s.slot_number}"
            )
    return None


@hard_rule("NO_ROOM_DOUBLE_BOOK")
def _no_room_double_book(candidate, committed, config, ctx) -> Optional[str]:
    for s in committed:
        if (
            s.room_id == candidate.room_id
            and s.day_of_week == candidate.day_of_week
            and s.slot_number in candidate.slot_numbers
        ):
            return (
                f"room {candidate.room_id} already booked "
                f"day {candidate.day_of_week} slot {s.slot_number}"
            )
    return None


@hard_rule("NO_GROUP_DOUBLE_BOOK")
def _no_group_double_book(candidate, committed, config, ctx) -> Optional[str]:
    for s in committed:
        if (
            s.student_group_id == candidate.student_group_id
            and s.day_of_week == candidate.day_of_week
            and s.slot_number in candidate.slot_numbers
        ):
            return (
                f"group {candidate.student_group_id} already scheduled "
                f"day {candidate.day_of_week} slot {s.slot_number}"
            )
    return None


def _published_conflict_for(candidate, ctx, resource_key, attr, label) -> Optional[str]:
    """Shared cross-timetable reservation check for one resource kind.

    A teacher, room, or group booked at (day, slot) in any published instance
    cannot be reused here, even if the other two dimensions differ. A multi-slot
    block checks every slot it spans.
    """
    if not ctx.reserved:
        return None
    rid = getattr(candidate, attr)
    for n in candidate.slot_numbers:
        key = (candidate.day_of_week, n)
        if (rid, *key) in ctx.reserved.get(resource_key, ()):
            return (
                f"{label} {rid} already booked in a published timetable "
                f"on day {candidate.day_of_week} slot {n}"
            )
    return None


@hard_rule("NO_CROSS_TIMETABLE_TEACHER_CONFLICT")
def _no_cross_timetable_teacher_conflict(candidate, committed, config, ctx) -> Optional[str]:
    return _published_conflict_for(candidate, ctx, "faculty", "faculty_id", "faculty")


@hard_rule("NO_CROSS_TIMETABLE_ROOM_CONFLICT")
def _no_cross_timetable_room_conflict(candidate, committed, config, ctx) -> Optional[str]:
    return _published_conflict_for(candidate, ctx, "room", "room_id", "room")


@hard_rule("NO_CROSS_TIMETABLE_GROUP_CONFLICT")
def _no_cross_timetable_group_conflict(candidate, committed, config, ctx) -> Optional[str]:
    return _published_conflict_for(candidate, ctx, "group", "student_group_id", "group")


@hard_rule("ROOM_CAPACITY_SUFFICIENT")
def _room_capacity_sufficient(candidate, committed, config, ctx) -> Optional[str]:
    room = ctx.room(candidate.room_id)
    group = ctx.group(candidate.student_group_id)
    if room and group and room.capacity < group.strength:
        return (
            f"room {room.name} capacity {room.capacity} "
            f"< group strength {group.strength}"
        )
    return None


@hard_rule("ROOM_REQUIREMENTS_MET")
def _room_requirements_met(candidate, committed, config, ctx) -> Optional[str]:
    """Reject a room that does not satisfy the subject's requirements.

    Generic resource requirements (app/engine/resource_requirements.py):
    ``requirements_json.session_type``/``room_types``/``min_capacity``/``features``
    are matched against the room's attributes; the legacy ``requires_lab``
    boolean is just shorthand for ``{"room_types": ["LAB"]}``.
    """
    from app.engine.resource_requirements import (
        effective_requirements, room_matches_requirements,
    )
    subject = ctx.subject(candidate.subject_id)
    room = ctx.room(candidate.room_id)
    if subject is None or room is None:
        return None
    ok, reason = room_matches_requirements(
        room, effective_requirements(subject))
    if not ok:
        return (
            f"subject {subject.name} requires {reason}; "
            f"room {room.name} does not match"
        )
    return None


@hard_rule("RESPECT_TEACHER_UNAVAILABILITY")
def _respect_teacher_unavailability(candidate, committed, config, ctx) -> Optional[str]:
    for w in ctx.unavailability(candidate.faculty_id):
        if w.day_of_week != candidate.day_of_week:
            continue
        if not _availability_window_applies(w, candidate.slot_date):
            continue
        if w.slot_start and w.slot_end:
            if candidate.start_time < w.slot_end and candidate.end_time > w.slot_start:
                return (
                    f"faculty {candidate.faculty_id} unavailable "
                    f"day {candidate.day_of_week} {w.slot_start}-{w.slot_end}"
                )
        else:
            return (
                f"faculty {candidate.faculty_id} unavailable "
                f"all day {candidate.day_of_week}"
            )
    return None


@hard_rule("FACULTY_MAX_HOURS_PER_DAY")
def _faculty_max_hours_per_day(candidate, committed, config, ctx) -> Optional[str]:
    """A teacher's ``max_hours_per_day``; a block counts as its full length."""
    faculty = ctx.faculty(candidate.faculty_id)
    if not faculty or not faculty.max_hours_per_day:
        return None
    day_count = sum(
        1 for s in committed
        if s.faculty_id == candidate.faculty_id
        and s.day_of_week == candidate.day_of_week
    ) + candidate.block_length
    if day_count > faculty.max_hours_per_day:
        return (
            f"faculty {candidate.faculty_id} would exceed daily cap "
            f"{faculty.max_hours_per_day} on day {candidate.day_of_week}"
        )
    return None


@hard_rule("FACULTY_MAX_HOURS_PER_WEEK")
def _faculty_max_hours_per_week(candidate, committed, config, ctx) -> Optional[str]:
    """A teacher's ``max_hours_per_week``; a block counts as its full length."""
    faculty = ctx.faculty(candidate.faculty_id)
    if not faculty or not faculty.max_hours_per_week:
        return None
    week_count = sum(
        1 for s in committed if s.faculty_id == candidate.faculty_id
    ) + candidate.block_length
    if week_count > faculty.max_hours_per_week:
        return (
            f"faculty {candidate.faculty_id} would exceed weekly cap "
            f"{faculty.max_hours_per_week}"
        )
    return None


@hard_rule("RESPECT_ROOM_BLACKOUT")
def _respect_room_blackout(candidate, committed, config, ctx) -> Optional[str]:
    for b in ctx.blackouts(candidate.room_id):
        # A recurring blackout matches by weekday; a date-specific one only
        # matches when the candidate carries an actual calendar date.
        if b.day_of_week is not None:
            applies = b.day_of_week == candidate.day_of_week
            when = f"every weekday {b.day_of_week}"
        elif b.date is not None:
            applies = candidate.slot_date is not None and b.date == candidate.slot_date
            when = f"on {b.date}"
        else:
            applies = False
            when = ""
        if not applies:
            continue
        if b.slot_start and b.slot_end:
            if candidate.start_time < b.slot_end and candidate.end_time > b.slot_start:
                return (
                    f"room {candidate.room_id} blacked out "
                    f"{b.slot_start}-{b.slot_end} {when}"
                )
        else:
            return f"room {candidate.room_id} blacked out all day {when}"
    return None


@hard_rule("SAME_SUBJECT_SAME_DAY")
def _same_subject_same_day(candidate, committed, config, ctx) -> Optional[str]:
    for s in committed:
        if (
            s.subject_id == candidate.subject_id
            and s.student_group_id == candidate.student_group_id
            and s.day_of_week == candidate.day_of_week
        ):
            return (
                f"subject {candidate.subject_id} already scheduled for group "
                f"{candidate.student_group_id} on day {candidate.day_of_week}"
            )
    return None


@hard_rule("CROSS_DEPT_DAILY_CAP")
def _cross_dept_daily_cap(candidate, committed, config, ctx) -> Optional[str]:
    """Optional hard rule driven by college feature flag.

    If the college has ``max_cross_dept_per_day`` configured in its
    ``config_json`` blob, refuse the placement when the same faculty would
    teach more than N sessions on this day.
    """
    if not ctx.settings or not candidate.is_cross_department:
        return None
    cap = (ctx.settings.config_json or {}).get("max_cross_dept_per_day")
    if cap is None:
        return None
    count = sum(
        1 for s in committed
        if s.faculty_id == candidate.faculty_id
        and s.day_of_week == candidate.day_of_week
    )
    if count >= int(cap):
        return (
            f"faculty {candidate.faculty_id} already teaches {count} "
            f"cross-dept sessions on day {candidate.day_of_week} (cap {cap})"
        )
    return None


# Register the data-driven rules after definition so the functions read top-down.
hard_rule("SUBJECT_TIME_PREFERENCE")(_subject_time_preference)
hard_rule("MAX_CONSECUTIVE_SAME_TEACHER")(_max_consecutive_same_teacher)
hard_rule("TEACHER_YEAR_RESTRICTION")(_teacher_year_restriction)
hard_rule("LAB_BATCH_ROTATION")(_lab_batch_rotation)
hard_rule("HOLIDAY_CALENDAR")(_holiday_calendar)
hard_rule("EXAM_DATE_SEPARATION")(_exam_date_separation)
hard_rule("CONTIGUOUS_LAB_SLOTS")(_contiguous_lab_slots)
