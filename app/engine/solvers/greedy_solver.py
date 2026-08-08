"""Greedy constraint-based solver.

For every session expanded from the subject-faculty-group assignments, the
solver scans all valid (day, slot, room) combinations in a stable order
and commits the first one that passes every hard constraint.

The solver reads the *college settings* singleton at construction time so
that any feature flag (e.g. ``allow_cross_dept_subjects``) actually affects
which sessions are generated.
"""
import random
from datetime import time, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.profiles import ResourceType
from app.models.constraints import HardConstraint
from app.models.rooms import Room, RoomType
from app.models.faculty import Faculty
from app.models.groups import StudentGroup
from app.models.subjects import Subject
from app.models.subject_assignments import SubjectAssignment
from app.models.generation import TimetableSlot, SessionType
from app.models.settings import CollegeSettings
from app.services.settings_service import get_settings
from app.engine.constraint_checker import ConstraintChecker, SlotCandidate
from app.engine.profile_resolver import ResolvedProfile


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
    ):
        self.subject_id = subject_id
        self.faculty_id = faculty_id
        self.student_group_id = student_group_id
        self.session_type = session_type
        self.requires_lab = requires_lab
        self.is_cross_department = is_cross_department


class GreedySolver:
    """Most-constrained-first greedy placement."""

    def __init__(
        self,
        db: Session,
        profile: ResolvedProfile,
        instance_id: int,
        seed: int | None = None,
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
        self.committed_slots: list[TimetableSlot] = []
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

    # ── session expansion ────────────────────────────────────
    def _build_sessions(self) -> list[SessionToSchedule]:
        """Expand every subject-assignment into N concrete sessions."""
        sessions: list[SessionToSchedule] = []
        profile_subject_ids = self._get_profile_resources(ResourceType.SUBJECT)
        if not profile_subject_ids:
            return sessions

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

            session_type = (
                SessionType.LAB if subject.requires_lab else SessionType.LECTURE
            )
            for _ in range(assignment.weekly_hours):
                sessions.append(SessionToSchedule(
                    subject_id=subject.id,
                    faculty_id=assignment.faculty_id,
                    student_group_id=assignment.group_id,
                    session_type=session_type,
                    requires_lab=subject.requires_lab,
                    is_cross_department=is_cross_dept,
                ))

        # most constrained first
        sessions.sort(key=lambda s: (
            0 if s.requires_lab else 1,
            0 if s.is_cross_department else 1,
        ))
        return sessions

    def _get_rooms(self, requires_lab: bool) -> list[Room]:
        room_ids = self._get_profile_resources(ResourceType.ROOM)
        query = select(Room).where(Room.id.in_(room_ids), Room.is_active == True)
        if requires_lab:
            query = query.where(Room.room_type == RoomType.LAB)
        return self.db.scalars(query).all()

    # ── main loop ────────────────────────────────────────────
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
            rooms = self._get_rooms(session.requires_lab)
            if self.rng is not None:
                rooms = list(rooms)
                self.rng.shuffle(rooms)

            for day in working_days:
                if placed:
                    break
                for slot_number, start_time, end_time in slot_times:
                    if placed:
                        break
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
                        )
                        if checker.is_valid(candidate):
                            self.committed_slots.append(TimetableSlot(
                                instance_id=self.instance_id,
                                slot_date=self._materialize_slot_date(day),
                                day_of_week=day,
                                slot_number=slot_number,
                                start_time=start_time,
                                end_time=end_time,
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
            print(f"Warning: {len(unscheduled)} sessions could not be scheduled")
        return self.committed_slots
