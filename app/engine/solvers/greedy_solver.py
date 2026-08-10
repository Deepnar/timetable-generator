"""Greedy constraint-based solver.

For every session expanded from the subject-faculty-group assignments, the
solver scans all valid (day, slot, room) combinations in a stable order
and commits the first one that passes every hard constraint.

The solver reads the *college settings* singleton at construction time so
that any feature flag (e.g. ``allow_cross_dept_subjects``) actually affects
which sessions are generated.
"""
import random
from collections import defaultdict
from datetime import time, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.profiles import ResourceType
from app.models.constraints import HardConstraint
from app.models.rooms import Room
from app.models.faculty import Faculty
from app.models.groups import StudentGroup
from app.models.subjects import Subject
from app.models.subject_assignments import SubjectAssignment
from app.models.generation import TimetableSlot, SessionType, VariationMode
from app.models.settings import CollegeSettings
from app.services.settings_service import get_settings
from app.engine.constraint_checker import ConstraintChecker, SlotCandidate
from app.engine.profile_resolver import ResolvedProfile
from app.engine.resource_requirements import (
    effective_requirements,
    subject_session_type,
    room_matches_requirements,
)


class SessionToSchedule:
    """One lecture/lab that needs a slot in the timetable."""

    def __init__(
        self,
        subject_id: int,
        faculty_id: int,
        student_group_id: int,
        session_type: SessionType,
        requires_lab: bool,
        is_cross_department: bool = False,
        block_length: int = 1,
        room_requirements: dict | None = None,
    ):
        self.subject_id = subject_id
        self.faculty_id = faculty_id
        self.student_group_id = student_group_id
        self.session_type = session_type
        self.requires_lab = requires_lab
        self.is_cross_department = is_cross_department
        # A lab block occupies ``block_length`` consecutive slots on one day
        # (1 == a single-slot session, the historical default).
        self.block_length = block_length
        # Declared room requirements (room_types/min_capacity/features); the
        # solver picks rooms that satisfy them. Empty = any active room.
        self.room_requirements = room_requirements or {}


class GreedySolver:
    """Most-constrained-first greedy placement."""

    def __init__(
        self,
        db: Session,
        profile: ResolvedProfile,
        instance_id: int,
        seed: int | None = None,
        variation: VariationMode = VariationMode.RANDOM,
    ):
        self.db = db
        # The resolved profile is the solver's entire input contract — either a
        # single profile or the merged view of a combination (see
        # app/engine/profile_resolver.py). Nothing is read from the DB by id.
        self.profile = profile
        self.profile_id = profile.profile_id
        self.instance_id = instance_id
        # A seed randomises the search order so the scheduler can generate
        # genuinely different candidate instances (see the diversity filter).
        self.seed = seed
        self.rng = random.Random(seed) if seed is not None else None
        # The instance strategy: "random" (seed-only diversity), "best", or a
        # gap-minimising criterion ("minimize-teacher-gaps" /
        # "minimize-student-gaps"). The criterion changes the search order of
        # the seeded instances so later candidates actually pursue the goal
        # instead of being random re-rolls.
        self.variation = variation
        self.committed_slots: list[TimetableSlot] = []
        # Number of requested sessions the solver could not place (0 when
        # everything was placed). Read by the scheduler to stamp a warning on
        # the run when a COMPLETED generation still dropped sessions.
        self.unplaced_count = 0
        # Populated by the scheduler with PUBLISHED reservations, keyed by
        # resource ("faculty" / "room" / "group") -> {(id, day, slot)}.
        self.reserved_conflicts: dict[str, set[tuple]] = {}
        self.params: dict = profile.params
        self.settings: CollegeSettings = get_settings(db)
        self._term_start: date | None = self._parse_term_start()

    def _get_param(self, key: str, default):
        return self.params.get(key, default)

    # ── calendar-date anchoring ──────────────────────────────
    def _parse_term_start(self) -> date | None:
        """Read the ``term_start`` profile param ("YYYY-MM-DD").

        The solver is a weekly template; anchoring it to a term start date
        lets date-based rules (availability windows, holiday blackouts) be
        evaluated against the concrete date of each slot in the first week.
        """
        raw = self._get_param("term_start", None)
        if not raw:
            return None
        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            return None

    def _materialize_slot_date(self, day_of_week: int) -> date | None:
        """Map a weekday to the calendar date it falls on in the term's week.

        Returns the first occurrence of ``day_of_week`` on/after the term
        start, or ``None`` when the profile has no ``term_start`` anchor.
        """
        if self._term_start is None:
            return None
        delta = (day_of_week - self._term_start.weekday()) % 7
        return self._term_start + timedelta(days=delta)

    # ── time structure ───────────────────────────────────────
    def _build_slot_times(self) -> list[tuple[int, time, time]]:
        slot_duration = self._get_param("slot_duration_minutes", 60)
        slots_per_day = self._get_param("slots_per_day", 7)
        lunch_after = self._get_param("lunch_break_after_slot", 3)
        lunch_duration = self._get_param("lunch_break_duration_minutes", 60)

        slots: list[tuple[int, time, time]] = []
        # Day start is configurable ("HH:MM") so the same engine can drive an
        # 8 AM school, a 9 AM college, or an evening program. Defaults to 09:00.
        current_hour, current_minute = self._parse_start_time(
            self._get_param("day_start_time", "09:00")
        )
        for i in range(1, slots_per_day + 1):
            start = time(current_hour, current_minute)
            total_minutes = current_hour * 60 + current_minute + slot_duration
            end = time(total_minutes // 60, total_minutes % 60)
            slots.append((i, start, end))
            current_hour = total_minutes // 60
            current_minute = total_minutes % 60
            if i == lunch_after:
                lunch_total = current_hour * 60 + current_minute + lunch_duration
                current_hour = lunch_total // 60
                current_minute = lunch_total % 60
        return slots

    @staticmethod
    def _parse_start_time(value) -> tuple[int, int]:
        """Parse a ``"HH:MM"`` day-start string into (hour, minute)."""
        try:
            hour_str, minute_str = str(value).split(":")
            return int(hour_str), int(minute_str)
        except (ValueError, AttributeError):
            return 9, 0

    def _get_working_days(self) -> list[int]:
        working_days_param = self._get_param(
            "working_days", ["MON", "TUE", "WED", "THU", "FRI"]
        )
        day_map = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}
        return [day_map[d] for d in working_days_param if d in day_map]

    def _get_profile_resources(self, resource_type: ResourceType) -> list[int]:
        return self.profile.resource_ids(resource_type)

    def _load_hard_constraints(self) -> list[HardConstraint]:
        """Active hard rules for the resolved profile (global + per-member)."""
        return list(self.profile.hard_constraints)

    def _load_soft_constraints(self) -> list:
        """Active soft rules for the resolved profile (global + per-member).

        The greedy solver reads them to order its (day, slot) scan so the
        default solver *pursues* the college's preferences during placement,
        not just ranks the result afterwards (see :meth:`_preference_scan`).
        """
        return list(self.profile.soft_constraints)

    def _is_exam_mode(self) -> bool:
        """Whether this profile schedules EXAM sessions instead of classes.

        A ``session_type`` parameter of ``"EXAM"`` switches the engine into
        exam mode: every subject-assignment becomes exactly one exam session,
        placed like any other slot but carrying ``SessionType.EXAM`` so
        exam-specific rules (e.g. ``EXAM_DATE_SEPARATION``) can act on it. The
        profile holds the groups taking exams, so one branch/year can run an
        exam timetable while the others keep their published class timetable.
        """
        return self._get_param("session_type", None) == "EXAM"

    def _lab_block_lengths(self) -> dict[int, int]:
        """Map subject_id -> contiguous-block length from CONTIGUOUS_LAB_SLOTS.

        The rule's config is ``{"block_lengths": {"<subject_id>": int},
        "default_block_length"?: int}``. ``default_block_length`` applies to
        every lab subject not explicitly listed, so the engine can form blocks
        for a whole department with one row.
        """
        lengths: dict[int, int] = {}
        default: int | None = None
        for rule in self._load_hard_constraints():
            rule_type = getattr(rule.constraint_type, "value", rule.constraint_type)
            if rule_type != "CONTIGUOUS_LAB_SLOTS":
                continue
            config = getattr(rule, "config_json", None) or {}
            if config.get("default_block_length"):
                default = int(config["default_block_length"])
            for key, value in (config.get("block_lengths") or {}).items():
                try:
                    lengths[int(key)] = int(value)
                except (ValueError, TypeError):
                    continue
        if default is not None:
            for subject_id in self._get_profile_resources(ResourceType.SUBJECT):
                lengths.setdefault(subject_id, default)
        return lengths

    # ── session expansion ────────────────────────────────────
    def _build_sessions(self) -> list[SessionToSchedule]:
        """Expand every subject-assignment into concrete sessions.

        A lab subject governed by a ``CONTIGUOUS_LAB_SLOTS`` rule is expanded
        into blocks of the configured size (its ``weekly_hours`` is split into
        full blocks plus a single-slot remainder), so each block becomes one
        multi-slot session instead of several isolated one-slot sessions.
        """
        sessions: list[SessionToSchedule] = []
        profile_subject_ids = self._get_profile_resources(ResourceType.SUBJECT)
        if not profile_subject_ids:
            return sessions

        block_lengths = self._lab_block_lengths()

        assignments = self.db.scalars(
            select(SubjectAssignment).where(
                SubjectAssignment.subject_id.in_(profile_subject_ids)
            )
        ).all()

        # Pre-fetch subjects to know which dept they belong to
        subjects = {
            s.id: s
            for s in self.db.scalars(
                select(Subject).where(Subject.id.in_(profile_subject_ids))
            ).all()
        }
        # Pre-fetch groups to detect cross-department sessions
        group_ids = {a.group_id for a in assignments}
        groups = {
            g.id: g
            for g in self.db.scalars(
                select(StudentGroup).where(StudentGroup.id.in_(group_ids))
            ).all()
        } if group_ids else {}

        for assignment in assignments:
            if not assignment.faculty_id or not assignment.weekly_hours:
                continue
            subject = subjects.get(assignment.subject_id)
            if not subject:
                continue
            group = groups.get(assignment.group_id)

            is_cross_dept = bool(
                group and group.department and subject.department
                and group.department != subject.department
            )

            # The "extreme flexibility" feature flag: if the college
            # has NOT opted in, we simply skip cross-department sessions.
            if is_cross_dept and not self.settings.allow_cross_dept_subjects:
                continue

            # Exam mode: one exam per subject-group, not weekly_hours copies.
            if self._is_exam_mode():
                sessions.append(SessionToSchedule(
                    subject_id=subject.id,
                    faculty_id=assignment.faculty_id,
                    student_group_id=assignment.group_id,
                    session_type=SessionType.EXAM,
                    requires_lab=False,
                    is_cross_department=is_cross_dept,
                    room_requirements=effective_requirements(subject),
                ))
                continue

            reqs = effective_requirements(subject)
            session_type = subject_session_type(subject)
            block_length = (
                block_lengths.get(subject.id)
                if session_type == SessionType.LAB else None
            )
            if block_length and block_length >= 2:
                full_blocks, remainder = divmod(assignment.weekly_hours, block_length)
                for _ in range(full_blocks):
                    sessions.append(SessionToSchedule(
                        subject_id=subject.id,
                        faculty_id=assignment.faculty_id,
                        student_group_id=assignment.group_id,
                        session_type=session_type,
                        requires_lab=subject.requires_lab,
                        is_cross_department=is_cross_dept,
                        block_length=block_length,
                        room_requirements=reqs,
                    ))
                for _ in range(remainder):
                    sessions.append(SessionToSchedule(
                        subject_id=subject.id,
                        faculty_id=assignment.faculty_id,
                        student_group_id=assignment.group_id,
                        session_type=session_type,
                        requires_lab=subject.requires_lab,
                        is_cross_department=is_cross_dept,
                        room_requirements=reqs,
                    ))
            else:
                for _ in range(assignment.weekly_hours):
                    sessions.append(SessionToSchedule(
                        subject_id=subject.id,
                        faculty_id=assignment.faculty_id,
                        student_group_id=assignment.group_id,
                        session_type=session_type,
                        requires_lab=subject.requires_lab,
                        is_cross_department=is_cross_dept,
                        room_requirements=reqs,
                    ))

        # most constrained first
        sessions.sort(key=lambda s: (
            0 if s.session_type == SessionType.LAB else 1,
            0 if s.is_cross_department else 1,
        ))
        # For a gap-minimising criterion, group each peer's sessions together
        # (all of one teacher's / group's sessions in a row) so the adjacency
        # scan in solve() can pack them into contiguous slots. Only the seeded
        # instances pursue the criterion — instance #1 stays the deterministic
        # baseline unless variation="best" is requested.
        peer_attr = self._criterion_peer_attr()
        if peer_attr and self.rng is not None:
            sessions.sort(key=lambda s: (
                0 if s.session_type == SessionType.LAB else 1,
                0 if s.is_cross_department else 1,
                getattr(s, peer_attr),
            ))
        return sessions

    def _get_rooms(self, requirements: dict) -> list[Room]:
        room_ids = self._get_profile_resources(ResourceType.ROOM)
        rooms = self.db.scalars(
            select(Room).where(Room.id.in_(room_ids), Room.is_active == True)
        ).all()
        return [r for r in rooms if room_matches_requirements(r, requirements)[0]]

    # ── main loop ────────────────────────────────────────────
    def _criterion_peer_attr(self) -> str | None:
        """The ``SessionToSchedule`` attribute a gap criterion peers by.

        ``"minimize-teacher-gaps"`` clusters a faculty member's sessions,
        ``"minimize-student-gaps"`` a group's. Any other variation returns
        ``None`` (plain seed-based diversity).
        """
        if self.variation == VariationMode.MINIMIZE_TEACHER_GAPS:
            return "faculty_id"
        if self.variation == VariationMode.MINIMIZE_STUDENT_GAPS:
            return "student_group_id"
        return None

    def _criterion_scan(
        self, session, working_days: list[int], slot_times: list
    ) -> list[tuple]:
        """Order the (day, slot) scan for a gap-minimising criterion.

        Days where the peer already teaches are scanned first, and within them
        slots are ordered by distance to the peer's existing placements, so the
        greedy solver fills around what is already there instead of starting
        over at the earliest free slot. Every (day, slot) is still considered —
        only the order changes, so the criterion can never make a session
        unschedulable.
        """
        peer_attr = self._criterion_peer_attr()
        # Instance #1 (seed=None) stays the deterministic baseline: the
        # criterion only reshapes the *seeded* re-rolls.
        if peer_attr is None or self.rng is None:
            return None

        peer_id = getattr(session, peer_attr)
        by_day: dict[int, list[int]] = defaultdict(list)
        for s in self.committed_slots:
            if (
                s.day_of_week is not None
                and getattr(s, peer_attr) == peer_id
            ):
                by_day[s.day_of_week].append(s.slot_number)

        def key(item):
            day, (sn, _st, _en) = item
            same_day = by_day.get(day)
            if same_day:
                # 0 = the peer already teaches that day → fill beside it.
                return (0, min(abs(sn - p) for p in same_day), sn)
            return (1, sn)

        return sorted(
            ((d, st) for d in working_days for st in slot_times), key=key
        )

    # ── soft-preference placement (greedy pursues preferences too) ──
    def _preference_scan(
        self, session, working_days: list[int], slot_times: list
    ) -> list[tuple] | None:
        """Order (day, slot) by the active soft constraints, if any.

        The greedy solver is deterministic: without this, it always takes the
        first valid slot and soft preferences only *rank* the finished result.
        This re-orders the scan so the default solver actively leans toward the
        college's stated preferences (morning slots for ``TEACHER_PREFERS_MORNING``,
        fresh days for ``DISTRIBUTE_SUBJECTS_EVENLY``, light days for
        ``BALANCE_TEACHER_LOAD``, etc.) while every candidate is still checked
        against the full hard-constraint checker, so validity is unchanged —
        only the search order.

        Returns ``None`` when no soft rule applies so the caller keeps its
        existing order (plain or gap-criterion). Rule weights scale each rule's
        contribution; heavier preferences win.
        """
        rules = self._load_soft_constraints()
        if not rules or not self.settings.enable_soft_constraint_scoring:
            return None

        # Collect (weight, per-slot bonus fn) for the applicable rules. Each
        # bonus fn returns 0.0 for "no preference", positive for "prefer", and
        # is called with (day, slot_number).
        scanners: list[tuple[float, Callable]] = []
        for rule in rules:
            if not getattr(rule, "is_active", True):
                continue
            rtype = getattr(rule.constraint_type, "value", rule.constraint_type)
            config = getattr(rule, "config_json", None) or {}
            weight = float(getattr(rule, "weight", 1.0) or 1.0)
            if weight <= 0:
                continue

            if rtype == "TEACHER_PREFERS_MORNING":
                boundary = config.get("boundary_slot", 4)
                faculty_id = config.get("faculty_id")
                if faculty_id is not None and session.faculty_id != faculty_id:
                    continue

                def bonus_morning(day, sn, boundary=boundary):
                    if sn <= boundary:
                        return 1.0 / boundary
                    return 0.0

                scanners.append((weight, bonus_morning))

            elif rtype == "DISTRIBUTE_SUBJECTS_EVENLY":
                subject_id = config.get("subject_id")
                if subject_id is not None and session.subject_id != subject_id:
                    continue
                if session.student_group_id is None:
                    continue
                used_days = {
                    s.day_of_week
                    for s in self.committed_slots
                    if s.student_group_id == session.student_group_id
                    and s.subject_id == session.subject_id
                    and s.day_of_week is not None
                }

                def bonus_distribute(day, sn, used=used_days):
                    return 0.0 if day in used else 1.0

                scanners.append((weight, bonus_distribute))

            elif rtype == "BALANCE_TEACHER_LOAD":
                faculty_id = config.get("faculty_id")
                if faculty_id is not None and session.faculty_id != faculty_id:
                    continue
                if session.faculty_id is None:
                    continue
                load: dict[int, int] = defaultdict(int)
                for s in self.committed_slots:
                    if s.faculty_id == session.faculty_id and s.day_of_week is not None:
                        load[s.day_of_week] += 1
                max_load = max(load.values()) if load else 0

                def bonus_balance(day, sn, load=load, max_load=max_load):
                    # Days under the current max get a boost; the lighter the
                    # day relative to the busiest, the stronger the preference.
                    cur = load.get(day, 0)
                    if max_load <= 0:
                        return 1.0
                    return 1.0 - (cur / (max_load + 1))

                scanners.append((weight, bonus_balance))

        if not scanners:
            return None

        def key(item):
            day, (sn, _st, _en) = item
            total = sum(weight * fn(day, sn) for weight, fn in scanners)
            return (-total, sn)

        return sorted(
            ((d, st) for d in working_days for st in slot_times), key=key
        )

    def solve(self) -> list[TimetableSlot]:
        checker = ConstraintChecker(
            self.db,
            self.committed_slots,
            settings=self.settings,
            reserved=self.reserved_conflicts,
            hard_constraints=self._load_hard_constraints(),
        )
        sessions = self._build_sessions()
        working_days = self._get_working_days()
        slot_times = self._build_slot_times()
        slot_lookup = {sn: (st, en) for sn, st, en in slot_times}
        max_slot_number = max(slot_lookup)
        # When seeded, randomise the search order so different seeds yield
        # different (still valid) timetables for the diversity filter.
        if self.rng is not None:
            working_days = list(working_days)
            slot_times = list(slot_times)
            self.rng.shuffle(working_days)
            self.rng.shuffle(slot_times)
        unscheduled: list[SessionToSchedule] = []

        for session in sessions:
            placed = False
            rooms = self._get_rooms(session.room_requirements)
            if self.rng is not None:
                rooms = list(rooms)
                self.rng.shuffle(rooms)

            # Order the (day, slot) scan. The gap criterion (variation) takes
            # precedence for seeded instances pursuing it; otherwise, when the
            # profile has active soft constraints, the scan leans toward those
            # preferences so the default greedy solver pursues them too.
            # Everything else keeps the plain day-then-slot order.
            scan = self._criterion_scan(session, working_days, slot_times)
            if scan is None:
                scan = self._preference_scan(session, working_days, slot_times)
            if scan is None:
                scan = [(d, st) for d in working_days for st in slot_times]
            for day, (slot_number, _start_time, _end_time) in scan:
                if placed:
                    break
                end_slot = slot_number + session.block_length - 1
                if end_slot > max_slot_number:
                    continue
                start_time = slot_lookup[slot_number][0]
                end_time = slot_lookup[end_slot][1]
                for room in rooms:
                    candidate = SlotCandidate(
                        instance_id=self.instance_id,
                        day_of_week=day,
                        slot_number=slot_number,
                        start_time=start_time,
                        end_time=end_time,
                        faculty_id=session.faculty_id,
                        room_id=room.id,
                        student_group_id=session.student_group_id,
                        subject_id=session.subject_id,
                        session_type=session.session_type,
                        slot_date=self._materialize_slot_date(day),
                        is_cross_department=session.is_cross_department,
                        block_length=session.block_length,
                    )
                    if checker.is_valid(candidate):
                        slot_date = self._materialize_slot_date(day)
                        for n in range(slot_number, end_slot + 1):
                            n_start, n_end = slot_lookup[n]
                            self.committed_slots.append(TimetableSlot(
                                instance_id=self.instance_id,
                                slot_date=slot_date,
                                day_of_week=day,
                                slot_number=n,
                                start_time=n_start,
                                end_time=n_end,
                                faculty_id=session.faculty_id,
                                room_id=room.id,
                                student_group_id=session.student_group_id,
                                subject_id=session.subject_id,
                                session_type=session.session_type,
                                is_manual_override=False,
                            ))
                        placed = True
                        break
            if not placed:
                unscheduled.append(session)

        if unscheduled:
            self.unplaced_count = len(unscheduled)
        return self.committed_slots
