"""Greedy constraint-based solver.

For every session expanded from the subject-faculty-group assignments, the
solver scans all valid (day, slot, room) combinations in a stable order
and commits the first one that passes every hard constraint.

The solver reads the *college settings* singleton at construction time so
that any feature flag (e.g. ``allow_cross_dept_subjects``) actually affects
which sessions are generated.
"""
from datetime import time
from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from app.models.profiles import (
    TimetableProfile,
    ProfileResource,
    ProfileParameter,
    ResourceType,
)
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

    def __init__(self, db: Session, profile_id: int, instance_id: int):
        self.db = db
        self.profile_id = profile_id
        self.instance_id = instance_id
        self.committed_slots: list[TimetableSlot] = []
        # Populated by the scheduler with PUBLISHED reservations, keyed by
        # resource ("faculty" / "room" / "group") -> {(id, day, slot)}.
        self.reserved_conflicts: dict[str, set[tuple]] = {}
        self.params: dict = {}
        self.settings: CollegeSettings = get_settings(db)
        self._load_params()

    # ── param loading ────────────────────────────────────────
    def _load_params(self) -> None:
        rows = self.db.scalars(
            select(ProfileParameter).where(
                ProfileParameter.profile_id == self.profile_id
            )
        ).all()
        for p in rows:
            if p.param_type == "INT":
                self.params[p.param_key] = int(p.param_value)
            elif p.param_type == "FLOAT":
                self.params[p.param_key] = float(p.param_value)
            elif p.param_type == "BOOLEAN":
                self.params[p.param_key] = p.param_value.lower() == "true"
            elif p.param_type == "JSON":
                import json
                self.params[p.param_key] = json.loads(p.param_value)
            else:
                self.params[p.param_key] = p.param_value

    def _get_param(self, key: str, default):
        return self.params.get(key, default)

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
        rows = self.db.scalars(
            select(ProfileResource).where(
                ProfileResource.profile_id == self.profile_id,
                ProfileResource.resource_type == resource_type,
            )
        ).all()
        return [r.resource_id for r in rows]

    def _load_hard_constraints(self) -> list[HardConstraint]:
        """Active hard constraints for this profile plus any global ones."""
        return self.db.scalars(
            select(HardConstraint).where(
                HardConstraint.is_active == True,
                or_(
                    HardConstraint.profile_id == self.profile_id,
                    HardConstraint.profile_id.is_(None),
                ),
            )
        ).all()

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
        unscheduled: list[SessionToSchedule] = []

        for session in sessions:
            placed = False
            rooms = self._get_rooms(session.requires_lab)

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
                            is_cross_department=session.is_cross_department,
                        )
                        if checker.is_valid(candidate):
                            self.committed_slots.append(TimetableSlot(
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
                                is_manual_override=False,
                            ))
                            placed = True
                            break
            if not placed:
                unscheduled.append(session)

        if unscheduled:
            print(f"Warning: {len(unscheduled)} sessions could not be scheduled")
        return self.committed_slots
