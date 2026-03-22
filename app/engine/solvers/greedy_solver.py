from datetime import time, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.profiles import (TimetableProfile, ProfileResource,
                                  ProfileParameter, ResourceType)
from app.models.rooms import Room
from app.models.faculty import Faculty
from app.models.groups import StudentGroup
from app.models.subjects import Subject
from app.models.generation import TimetableSlot, SessionType
from app.engine.constraint_checker import ConstraintChecker, SlotCandidate


class SessionToSchedule:
    """
    Represents one lecture/lab that needs to be placed in the timetable.
    Created by expanding subject hours_per_week into individual sessions.
    """
    def __init__(
        self,
        subject_id: int,
        faculty_id: int,
        student_group_id: int,
        session_type: SessionType,
        requires_lab: bool
    ):
        self.subject_id = subject_id
        self.faculty_id = faculty_id
        self.student_group_id = student_group_id
        self.session_type = session_type
        self.requires_lab = requires_lab


class GreedySolver:
    """
    Assigns sessions to slots one at a time.
    For each session picks the first valid (day, slot, room) combination.
    Most constrained sessions (labs, limited faculty) are placed first.
    """

    def __init__(self, db: Session, profile_id: int, instance_id: int):
        self.db = db
        self.profile_id = profile_id
        self.instance_id = instance_id
        self.committed_slots: list[TimetableSlot] = []
        self.params = {}
        self._load_params()

    def _load_params(self):
        """Load profile parameters into a simple dict."""
        params = self.db.scalars(
            select(ProfileParameter).where(
                ProfileParameter.profile_id == self.profile_id
            )
        ).all()
        for p in params:
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

    def _build_slot_times(self) -> list[tuple[int, time, time]]:
        """
        Returns list of (slot_number, start_time, end_time) tuples.
        Built from slot_duration_minutes and slots_per_day parameters.
        Default: 7 slots of 60 mins starting at 9am.
        """
        slot_duration = self._get_param("slot_duration_minutes", 60)
        slots_per_day = self._get_param("slots_per_day", 7)
        lunch_after = self._get_param("lunch_break_after_slot", 3)
        lunch_duration = self._get_param("lunch_break_duration_minutes", 60)

        slots = []
        current_hour = 9
        current_minute = 0

        for i in range(1, slots_per_day + 1):
            start = time(current_hour, current_minute)
            total_minutes = current_hour * 60 + current_minute + slot_duration
            end = time(total_minutes // 60, total_minutes % 60)
            slots.append((i, start, end))

            current_hour = total_minutes // 60
            current_minute = total_minutes % 60

            # add lunch break after configured slot
            if i == lunch_after:
                lunch_total = current_hour * 60 + current_minute + lunch_duration
                current_hour = lunch_total // 60
                current_minute = lunch_total % 60

        return slots

    def _get_working_days(self) -> list[int]:
        """
        Returns list of day numbers to schedule on.
        Default: Mon-Fri (0-4).
        """
        working_days_param = self._get_param(
            "working_days",
            ["MON", "TUE", "WED", "THU", "FRI"]
        )
        day_map = {
            "MON": 0, "TUE": 1, "WED": 2,
            "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6
        }
        return [day_map[d] for d in working_days_param if d in day_map]

    def _get_profile_resources(self, resource_type: ResourceType) -> list[int]:
        """Returns list of resource IDs of given type linked to this profile."""
        resources = self.db.scalars(
            select(ProfileResource).where(
                ProfileResource.profile_id == self.profile_id,
                ProfileResource.resource_type == resource_type
            )
        ).all()
        return [r.resource_id for r in resources]

    def _build_sessions(self) -> list[SessionToSchedule]:
        """
        Expands subjects into individual sessions based on hours_per_week.
        A subject needing 4 hours/week becomes 4 SessionToSchedule objects.
        Labs get double slot duration — counted as 2 sessions.
        """
        sessions = []

        subject_ids = self._get_profile_resources(ResourceType.SUBJECT)
        faculty_ids = self._get_profile_resources(ResourceType.FACULTY)
        group_ids = self._get_profile_resources(ResourceType.STUDENT_GROUP)

        subjects = self.db.scalars(
            select(Subject).where(Subject.id.in_(subject_ids))
        ).all()

        # simple assignment — first faculty to first group
        # in a real system this would come from a subject_assignments table
        # for now we pair them round-robin
        faculty_index = 0
        group_index = 0

        for subject in subjects:
            if not faculty_ids or not group_ids:
                continue

            faculty_id = faculty_ids[faculty_index % len(faculty_ids)]
            group_id = group_ids[group_index % len(group_ids)]

            session_type = (
                SessionType.LAB if subject.requires_lab
                else SessionType.LECTURE
            )

            # each hour_per_week = one session
            for _ in range(subject.hours_per_week):
                sessions.append(SessionToSchedule(
                    subject_id=subject.id,
                    faculty_id=faculty_id,
                    student_group_id=group_id,
                    session_type=session_type,
                    requires_lab=subject.requires_lab
                ))

            faculty_index += 1
            group_index += 1

        # most constrained first — labs before lectures
        sessions.sort(key=lambda s: (0 if s.requires_lab else 1))
        return sessions

    def _get_rooms(self, requires_lab: bool) -> list[Room]:
        """Returns available rooms filtered by type if lab is required."""
        room_ids = self._get_profile_resources(ResourceType.ROOM)
        query = select(Room).where(
            Room.id.in_(room_ids),
            Room.is_active == True
        )
        if requires_lab:
            from app.models.rooms import RoomType
            query = query.where(Room.room_type == RoomType.LAB)
        return self.db.scalars(query).all()

    def solve(self) -> list[TimetableSlot]:
        """
        Main solver loop.
        Returns list of TimetableSlot objects ready to be committed to DB.
        """
        checker = ConstraintChecker(self.db, self.committed_slots)
        sessions = self._build_sessions()
        working_days = self._get_working_days()
        slot_times = self._build_slot_times()
        unscheduled = []

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
                            session_type=session.session_type
                        )

                        if checker.is_valid(candidate):
                            slot = TimetableSlot(
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
                                is_manual_override=False
                            )
                            self.committed_slots.append(slot)
                            placed = True
                            break

            if not placed:
                unscheduled.append(session)

        if unscheduled:
            print(f"Warning: {len(unscheduled)} sessions could not be scheduled")

        return self.committed_slots