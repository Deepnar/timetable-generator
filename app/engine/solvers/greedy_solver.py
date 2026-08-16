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
from typing import Callable
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
        batch_number: int | None = None,
        parallel_key=None,
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
        # Parallel practicals (DD-024): which lab batch (1..N) this session
        # covers. Siblings sharing a ``parallel_key`` must be placed at the
        # same time in distinct rooms. None = whole-division session.
        self.batch_number = batch_number
        self.parallel_key = parallel_key
        # Window identity (A1): which lab window this session belongs to. A
        # window is (group_id, period_number); its members — different batches,
        # possibly different subjects — share this key so the checker can
        # recognise siblings without requiring the same subject.
        self.window_key: str | None = None
        # For a windowed lab base session: batch -> (subject_id, faculty_id)
        # for ONE window (e.g. CG lab: {1: (CG, SuS), 2: (CG, PD)} for D1D2,
        # IIS: {3: (IIS, PM), 4: (IIS, PM)} for D3D4 in the same window). The
        # expansion creates one parallel session per entry, each carrying its
        # own subject. Replaces the old single-subject ``parallel_batch_map``.
        self.window_members: dict[int, tuple] | None = None
        # DD-044: per representative batch, the FULL batch list a merged
        # single-teacher member covers (e.g. "Lab DWM A1A2 SG" -> {1: [1, 2]}).
        # The representative batch is what the placed slot records.
        self.window_batches: dict[int, list[int]] = {}
        # The batch coverage of an expanded member session (defaults to the
        # single batch); useful for UI rendering of merged pairs.
        self.batch_list: list[int] | None = None


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
        """The grid's slot times, verbatim when the profile declares them.

        A profile that imports a real grid carries ``slot_times`` — the exact
        ``[["08:30","09:30"], ...]`` rows from the published grid, one per
        teachable slot. When present, they are read verbatim (A2); the
        synthetic ``day_start_time``/``slot_duration_minutes``/lunch arithmetic
        below is the fallback for colleges that never provide a grid.
        """
        verbatim = self._get_param("slot_times", None)
        if verbatim:
            slots: list[tuple[int, time, time]] = []
            try:
                for i, (start_s, end_s) in enumerate(verbatim, start=1):
                    h1, m1 = (int(x) for x in str(start_s).split(":"))
                    h2, m2 = (int(x) for x in str(end_s).split(":"))
                    slots.append((i, time(h1, m1), time(h2, m2)))
            except (TypeError, ValueError):
                slots = []
            if slots:
                return slots

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

    def _break_slots(self) -> set[int]:
        """The slot numbers this profile's grid reserves as a break (A2).

        A break is a numbered slot whose position varies per division (measured
        across the 46 real grids: slot 4×45, 5×51, 3×41, 6×28). Sessions must
        never be placed there; the scan skips them and the
        ``NO_TEACHING_IN_BREAK_SLOT`` validator rejects any that sneak through.
        """
        raw = self._get_param("break_slots", [])
        try:
            return {int(s) for s in raw}
        except (TypeError, ValueError):
            return set()

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
        days = [day_map[d] for d in working_days_param if d in day_map]
        # saturday_policy: NONE (default) — Saturday is not a teaching day;
        # FULL — it is a normal day. ACTIVITY_ONLY keeps Saturday in the grid
        # but only for sessions that are not lectures/labs (see
        # :meth:`_is_activity_session`), matching real colleges where Saturday
        # hosts IP/co-curricular/notional activity.
        policy = str(self._get_param("saturday_policy", "NONE")).upper()
        if policy == "FULL":
            return days
        if policy == "ACTIVITY_ONLY":
            # Saturday stays available; per-session filtering happens in the
            # scan via :meth:`_day_allowed_for`.
            return days
        return [d for d in days if d != 5]

    @staticmethod
    def _is_activity_session(session) -> bool:
        """Whether a session is non-teaching "activity" (IP/co-curricular).

        Used by the ``saturday_policy=ACTIVITY_ONLY`` rule: only activity
        sessions may land on Saturday.
        """
        stype = getattr(session, "session_type", None)
        value = getattr(stype, "value", stype)
        return value in ("IP", "ACTIVITY", "CUSTOM", "SEMINAR", "EVENT")

    def _day_allowed_for(self, day: int, session) -> bool:
        """Whether ``day`` is a legal placement day for this session.

        The ``saturday_policy`` param gates Saturday specifically:
        ``ACTIVITY_ONLY`` admits Saturday for activity sessions and nothing
        else; ``FULL`` admits it for everything. Non-Saturday days are always
        allowed (working_days already excludes days the college does not teach).
        """
        if day != 5:
            return True
        policy = str(self._get_param("saturday_policy", "NONE")).upper()
        if policy == "FULL":
            return True
        if policy == "ACTIVITY_ONLY":
            return self._is_activity_session(session)
        return False

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

        Either a ``session_type`` parameter of ``"EXAM"`` (the explicit form)
        or a profile with ``scope_type == EXAM`` (the convenient form — an
        admin picks the scope and exam mode is implied) switches the engine
        into exam mode: every subject-assignment becomes exactly one exam
        session, placed like any other slot but carrying ``SessionType.EXAM``
        so exam-specific rules (e.g. ``EXAM_DATE_SEPARATION``) can act on it.
        The profile holds the groups taking exams, so one branch/year can run
        an exam timetable while the others keep their published class timetable.
        """
        if self._get_param("session_type", None) == "EXAM":
            return True
        return getattr(self.profile, "scope_type", None) == "EXAM"

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

        # The profile defines WHICH classes to schedule, not just which
        # subjects. A per-class (DIVISION) profile attaches one group, so we
        # must only expand that group's assignments — filtering by subject alone
        # would schedule every division that shares the subject. When the
        # profile has no group resources, keep the legacy subject-only behavior.
        profile_group_ids = self._get_profile_resources(ResourceType.STUDENT_GROUP)

        block_lengths = self._lab_block_lengths()

        query = select(SubjectAssignment).where(
            SubjectAssignment.subject_id.in_(profile_subject_ids)
        )
        if profile_group_ids:
            query = query.where(SubjectAssignment.group_id.in_(profile_group_ids))
        assignments = self.db.scalars(query).all()

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

        # Group batched lab rows into WINDOWS (A1). A window is
        # (group_id, period_number); its members are (batch_number, subject_id,
        # faculty_id) rows sharing that period — two different subjects can be
        # co-located in one window (COMP-TE-D day 0: CG->D1D2 + IIS->D3D4).
        # Non-batched rows expand independently as before.
        window_rows: dict[tuple[int, int], list] = {}
        non_batched: list = []
        for a in assignments:
            if getattr(a, "batch_number", None) is not None:
                period = getattr(a, "period_number", None) or 1
                window_rows.setdefault((a.group_id, period), []).append(a)
            else:
                non_batched.append(a)

        for (group_id, period), rows in sorted(window_rows.items()):
            # Dedupe by batch: the real grid can list the same batch twice for
            # one subject across a 2-slot window; keep the first row's subject.
            by_batch: dict[int, object] = {}
            block_length = None
            for r in rows:
                b = int(r.batch_number)
                if b not in by_batch:
                    by_batch[b] = r
                if getattr(r, "block_length", None):
                    block_length = int(r.block_length)
            members = {b: (r.subject_id, r.faculty_id)
                       for b, r in by_batch.items()}
            # DD-044: a single-teacher pair ("Lab DWM A1A2 SG 324") emits one
            # member row per batch sharing one faculty — a window those members
            # can never co-locate in (one teacher cannot run two batches at
            # once). The college's grid means ONE session covering the pair:
            # merge members that share (subject, faculty) into a single session
            # carrying the full batch list, so the window becomes co-locatable
            # and the pair's students are still covered. The representative
            # batch (the lowest) is what the placed slot records.
            merged_members: dict[int, tuple] = {}
            merged_batches: dict[int, list[int]] = {}
            rep_for_member: dict[tuple, int] = {}
            for b, member in sorted(members.items()):
                rep = rep_for_member.get(member)
                if rep is None:
                    rep = b
                    rep_for_member[member] = rep
                    merged_members[rep] = member
                    merged_batches[rep] = []
                merged_batches[rep].append(b)
            base = by_batch[min(merged_members)]
            base_session = self._make_window_base(
                base, merged_members, group_id, period, subjects, groups,
                block_length, merged_batches=merged_batches)
            if base_session is not None:
                sessions.append(base_session)

        for assignment in non_batched:
            self._append_base_sessions(
                sessions, assignment, subjects, groups,
                parallel_batch_map=None,
            )

        # Most-constrained-first (A6): order by room scarcity x faculty
        # scarcity x group load x block size. The sessions that are hardest to
        # place go first so they get the best slots; the old two-boolean sort
        # (is-lab, is-cross-dept) ignored every factor that actually decides
        # feasibility. The room domain mirrors _get_rooms: labs match the lab
        # pool, non-lab sessions with a home room are restricted to it.
        room_pool_ids = self._get_profile_resources(ResourceType.ROOM)
        room_pool = [
            r for r in self.db.scalars(
                select(Room).where(Room.id.in_(room_pool_ids),
                                   Room.is_active == True)
            ).all()
        ]
        faculty_demand: dict[int, int] = defaultdict(int)
        group_demand: dict[int, int] = defaultdict(int)
        for a in assignments:
            if a.faculty_id is not None:
                faculty_demand[a.faculty_id] += 1
            if a.group_id is not None:
                group_demand[a.group_id] += 1

        def _room_count(s) -> int:
            matching = [r for r in room_pool
                        if room_matches_requirements(r, s.room_requirements)[0]]
            if s.session_type != SessionType.LAB:
                g = groups.get(s.student_group_id)
                if g is not None:
                    home = {g.home_room_id, g.home_room_secondary_id}
                    home = {i for i in home if i is not None}
                    if home:
                        restricted = [r for r in matching if r.id in home]
                        if restricted:
                            return len(restricted)
            return len(matching)

        sessions.sort(key=lambda s: (
            _room_count(s),
            -faculty_demand.get(s.faculty_id, 0),
            -group_demand.get(s.student_group_id, 0),
            -s.block_length,
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

    def _make_window_base(self, base, members, group_id, period, subjects,
                          groups, block_length=None,
                          merged_batches: dict[int, list[int]] | None = None
                          ) -> SessionToSchedule | None:
        """Build the base session for one lab window.

        ``members`` maps batch_number -> (subject_id, faculty_id). The window
        is expanded into one parallel session per member by
        :meth:`_expand_lab_batches`; each member carries its own subject and
        shares ``window_key`` so the checker treats them as siblings.
        ``merged_batches`` (DD-044) maps a representative batch to the full
        batch list a merged member covers (a single-teacher pair).
        """
        subject = subjects.get(base.subject_id)
        if subject is None:
            return None
        group = groups.get(group_id)
        is_cross_dept = bool(
            group and group.department and subject.department
            and group.department != subject.department
        )
        if is_cross_dept and not self.settings.allow_cross_dept_subjects:
            return None
        if self._is_exam_mode():
            return SessionToSchedule(
                subject_id=subject.id,
                faculty_id=base.faculty_id,
                student_group_id=group_id,
                session_type=SessionType.EXAM,
                requires_lab=False,
                is_cross_department=is_cross_dept,
                room_requirements=effective_requirements(subject),
            )
        reqs = effective_requirements(subject)
        block_lengths = self._lab_block_lengths()
        if block_length is None:
            block_length = block_lengths.get(subject.id)
        s = SessionToSchedule(
            subject_id=subject.id,
            faculty_id=base.faculty_id,
            student_group_id=group_id,
            session_type=SessionType.LAB,
            requires_lab=subject.requires_lab,
            is_cross_department=is_cross_dept,
            block_length=block_length or 1,
            room_requirements=reqs,
        )
        s.window_members = dict(members)
        s.window_key = f"w{group_id}:{period}"
        s.parallel_key = ("window", group_id, period)
        s.window_batches = dict(merged_batches or {})
        return s

    # ── parallel practicals (batches) ─────────────────────────
    def _append_base_sessions(self, sessions, assignment, subjects, groups,
                              parallel_batch_map=None):
        """Expand one assignment row into base sessions (block-aware).

        ``parallel_batch_map`` (batch -> faculty) is set for a lab period with
        per-batch faculty; the batch expansion (:meth:`_expand_lab_batches`)
        turns the base block into one parallel session per batch.
        """
        if not assignment.faculty_id or not assignment.weekly_hours:
            return
        subject = subjects.get(assignment.subject_id)
        if not subject:
            return
        group = groups.get(assignment.group_id)

        is_cross_dept = bool(
            group and group.department and subject.department
            and group.department != subject.department
        )
        if is_cross_dept and not self.settings.allow_cross_dept_subjects:
            return
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
            return

        reqs = effective_requirements(subject)
        session_type = subject_session_type(subject)
        block_lengths = self._lab_block_lengths()
        block_length = (
            block_lengths.get(subject.id)
            if session_type == SessionType.LAB else None
        )

        def _mk(block_len):
            s = SessionToSchedule(
                subject_id=subject.id,
                faculty_id=assignment.faculty_id,
                student_group_id=assignment.group_id,
                session_type=session_type,
                requires_lab=subject.requires_lab,
                is_cross_department=is_cross_dept,
                block_length=block_len or 1,
                room_requirements=reqs,
            )
            if parallel_batch_map:
                s.parallel_batch_map = dict(parallel_batch_map)
            return s

        if block_length and block_length >= 2:
            full_blocks, remainder = divmod(assignment.weekly_hours, block_length)
            for _ in range(full_blocks):
                sessions.append(_mk(block_length))
            for _ in range(remainder):
                sessions.append(_mk(1))
        else:
            for _ in range(assignment.weekly_hours):
                sessions.append(_mk(1))

    def _group_by_id(self, group_id: int):
        if not hasattr(self, "_group_cache"):
            self._group_cache: dict[int, StudentGroup] = {}
        if group_id not in self._group_cache:
            self._group_cache[group_id] = self.db.get(StudentGroup, group_id)
        return self._group_cache[group_id]

    def _derive_lab_batch_count(self, group_id: int) -> int:
        """How many lab batches a division's practicals split into.

        A profile ``lab_batches`` parameter overrides the college default,
        which is derived from the group's year: FE (year 1) → 3 batches,
        SE/TE/BE → 2 lab groups. ``1`` means no parallelisation (whole-division
        practicals, the legacy behaviour).
        """
        raw = self._get_param("lab_batches", None)
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
        group = self._group_by_id(group_id)
        if group is not None and group.year == 1:
            return 3
        return 2

    def _lab_batch_faculty(self, subject_id, group_id, base_faculty_id) -> list:
        """Faculty ids, one per lab batch, for a (subject, group) practical.

        Assignment rows with ``batch_number`` set are authoritative (the real
        grids declare one faculty per batch, e.g. "Lab CG D1 D2 SuS/PD"). When
        none are set, the batch count is derived from the group's year and the
        remaining batches get the next QUALIFIED faculty in the profile's pool
        — only teachers with a ``faculty_subject_competency`` row for the
        subject (A9/B4). Fabricating staff from idle strangers (the old
        lowest-id fallback) silently misassigned practicals to teachers who
        had never taught the subject.
        """
        rows = self.db.scalars(
            select(SubjectAssignment).where(
                SubjectAssignment.subject_id == subject_id,
                SubjectAssignment.group_id == group_id,
                SubjectAssignment.batch_number.isnot(None),
            )
        ).all()
        if rows:
            by_batch = {int(r.batch_number): r.faculty_id for r in rows if r.faculty_id}
            if by_batch:
                return [by_batch.get(b) for b in range(1, max(by_batch) + 1)]
        count = self._derive_lab_batch_count(group_id)
        if count <= 1:
            return [base_faculty_id]
        from app.models.faculty_subject_competency import FacultySubjectCompetency
        qualified_ids = set(
            self.db.scalars(
                select(FacultySubjectCompetency.faculty_id).where(
                    FacultySubjectCompetency.subject_id == subject_id)
            ).all()
        )
        others = sorted(
            f for f in self._get_profile_resources(ResourceType.FACULTY)
            if f != base_faculty_id and f in qualified_ids
        )
        # Never fabricate: if the pool has no qualified teacher for the extra
        # batches, the practical stays whole-division rather than inventing
        # staff (B4).
        if not others:
            return [base_faculty_id]
        return [base_faculty_id] + others[: count - 1]

    def _expand_lab_batches(self, sessions: list[SessionToSchedule]) -> list[SessionToSchedule]:
        """Turn lab windows and whole-division lab blocks into per-batch sessions.

        A **window** base session (``window_members`` set) expands into one
        sibling session per batch, each carrying its own subject/faculty and
        sharing ``window_key`` + ``parallel_key`` (A1). A legacy whole-division
        lab block (no window members, ``block_length >= 2``) expands into
        auto-derived batches from the pool as before. The greedy solver places
        siblings at the same time in distinct rooms (see
        :meth:`_place_parallel_group`). Single-slot lab remainders and all
        non-lab sessions pass through unchanged.
        """
        if self._is_exam_mode():
            return sessions
        expanded: list[SessionToSchedule] = []
        for s in sessions:
            if s.session_type == SessionType.LAB and s.window_members:
                # One parallel session per member, each with its own subject.
                # A merged member (DD-044) covers several batches with one
                # teacher; the representative batch is recorded on the slot and
                # the full coverage list rides along for the UI/rotation.
                for b, (subj_id, fid) in sorted(s.window_members.items()):
                    member_subject = self.db.get(Subject, subj_id)
                    reqs = effective_requirements(member_subject) if member_subject else s.room_requirements
                    expanded.append(SessionToSchedule(
                        subject_id=subj_id,
                        faculty_id=fid,
                        student_group_id=s.student_group_id,
                        session_type=SessionType.LAB,
                        requires_lab=bool(member_subject and member_subject.requires_lab),
                        is_cross_department=s.is_cross_department,
                        block_length=s.block_length,
                        room_requirements=reqs,
                        batch_number=b,
                        parallel_key=s.parallel_key,
                    ))
                    expanded[-1].window_key = s.window_key
                    expanded[-1].batch_list = s.window_batches.get(b, [b])
                continue
            if s.session_type == SessionType.LAB and s.block_length >= 2:
                # No window members: derive faculty from the pool (auto batches).
                facs = self._lab_batch_faculty(
                    s.subject_id, s.student_group_id, s.faculty_id)
                if len(facs) >= 2:
                    for b, fid in enumerate(facs, start=1):
                        expanded.append(SessionToSchedule(
                            subject_id=s.subject_id,
                            faculty_id=fid,
                            student_group_id=s.student_group_id,
                            session_type=s.session_type,
                            requires_lab=s.requires_lab,
                            is_cross_department=s.is_cross_department,
                            block_length=s.block_length,
                            room_requirements=s.room_requirements,
                            batch_number=b,
                            parallel_key=("lab", id(s)),
                        ))
                        expanded[-1].window_key = f"auto-{s.subject_id}-{id(s)}"
                    continue
            expanded.append(s)
        return expanded

    def _scan(self, session, working_days: list[int], slot_times: list) -> list[tuple]:
        """Order the (day, slot) scan: gap criterion → soft preference → spread."""
        scan = self._criterion_scan(session, working_days, slot_times)
        if scan is None:
            scan = self._preference_scan(session, working_days, slot_times)
        if scan is None:
            scan = self._group_balance_scan(session, working_days, slot_times)
        return scan

    def _parallel_rooms(self, group, day, slot_number, start_time, end_time,
                        rooms, checker):
        """Pick one distinct room per batch so the whole group can co-exist.

        Each member's candidate must pass the full checker against the
        committed slots (siblings are not committed yet, so they do not
        conflict), the rooms must be distinct, and no two batches may share a
        faculty. Returns ``[(session, room), ...]`` or ``None``.
        """
        options: list[tuple[SessionToSchedule, list]] = []
        for session in group:
            member_options = []
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
                    batch_number=session.batch_number,
                    window_key=session.window_key,
                )
                if checker.is_valid(candidate):
                    member_options.append((room, candidate))
            if not member_options:
                return None
            options.append((session, member_options))
        options.sort(key=lambda o: len(o[1]))

        used_rooms: set[int] = set()
        used_faculty: set = set()
        chosen: list[tuple[SessionToSchedule, object]] = []

        def backtrack(i: int) -> bool:
            if i == len(options):
                return True
            session, member_options = options[i]
            for room, _cand in member_options:
                if room.id in used_rooms:
                    continue
                if session.faculty_id is not None and session.faculty_id in used_faculty:
                    continue
                used_rooms.add(room.id)
                if session.faculty_id is not None:
                    used_faculty.add(session.faculty_id)
                chosen.append((session, room))
                if backtrack(i + 1):
                    return True
                chosen.pop()
                used_rooms.discard(room.id)
                if session.faculty_id is not None:
                    used_faculty.discard(session.faculty_id)
            return False

        return chosen if backtrack(0) else None

    def _place_parallel_group(self, group, checker, working_days, slot_times,
                              slot_lookup, max_slot_number) -> bool:
        """Place all batches of a lab period at the same time in distinct rooms.

        Returns True when placed. The whole division is occupied during the
        window (every batch is in a lab), so NO_GROUP_DOUBLE_BOOK naturally
        keeps other subjects out; max-one-lab-per-day falls out because the
        division has no free student during any lab period.
        """
        base = group[0]
        block_length = base.block_length
        rooms = self._get_rooms(base.room_requirements, session=base)
        if len(rooms) < len(group):
            return False
        if self.rng is not None:
            rooms = list(rooms)
            self.rng.shuffle(rooms)
        # The saturday_policy may forbid Saturday for this session type.
        group_working_days = [
            d for d in working_days if self._day_allowed_for(d, base)
        ]
        if not group_working_days:
            return False
        for day, (slot_number, _st, _en) in self._scan(
                base, group_working_days, slot_times):
            end_slot = slot_number + block_length - 1
            if end_slot > max_slot_number:
                continue
            start_time = slot_lookup[slot_number][0]
            end_time = slot_lookup[end_slot][1]
            placement = self._parallel_rooms(
                group, day, slot_number, start_time, end_time, rooms, checker)
            if placement is None:
                continue
            slot_date = self._materialize_slot_date(day)
            for session, room in placement:
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
                        batch_number=session.batch_number,
                        window_key=session.window_key,
                    ))
            return True
        return False

    def _get_rooms(self, requirements: dict, session=None) -> list[Room]:
        """Candidate rooms for a session, in preference order.

        For a **non-lab** session, the room domain is hard-restricted to the
        division's home rooms (``StudentGroup.home_room_id`` +
        ``home_room_secondary_id``) when the group has them (A5). This is a
        restriction, not a sort order: lectures stay in the college's venue
        instead of scattering across the whole pool. If the group has no home
        room (or the session is a lab, which lives in lab rooms), the general
        pool applies. ``preferred_rooms`` still sorts within whatever domain
        survives so a custom venue preference is respected.
        """
        room_ids = self._get_profile_resources(ResourceType.ROOM)
        rooms = self.db.scalars(
            select(Room).where(Room.id.in_(room_ids), Room.is_active == True)
        ).all()
        matching = [r for r in rooms if room_matches_requirements(r, requirements)[0]]

        is_lab = (
            getattr(session, "session_type", None) is not None
            and getattr(session.session_type, "value", session.session_type) == "LAB"
        )
        home_ids = self._home_room_ids(session)
        if home_ids and not is_lab:
            home_matching = [r for r in matching if r.id in home_ids]
            if home_matching:
                # Hard restriction: only the venue. If the venue rooms are all
                # taken at a slot the session simply does not fit there and the
                # scan moves on — no silent drift to a random room.
                matching = home_matching

        # Preferred_rooms (profile param): order the class's real venue rooms
        # first so sessions land in the same rooms the college uses, not the
        # first arbitrary room in the pool.
        preferred = self._get_param("preferred_rooms", None)
        if preferred:
            try:
                pref_set = {int(r) for r in preferred}
            except (TypeError, ValueError):
                pref_set = set()
            matching.sort(key=lambda r: (0 if r.id in pref_set else 1, r.id))
        return matching

    def _home_room_ids(self, session) -> set[int]:
        """The division's home-room ids (``home_room_id`` + secondary), if any.

        Read from the ``StudentGroup`` row; a group without a declared venue
        returns an empty set, keeping the legacy free-pool behaviour.
        """
        group_id = getattr(session, "student_group_id", None)
        if group_id is None:
            return set()
        group = self.db.get(StudentGroup, group_id)
        if group is None:
            return set()
        ids = {group.home_room_id, group.home_room_secondary_id}
        return {i for i in ids if i is not None}

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
    def _group_balance_scan(
        self, session, working_days: list[int], slot_times: list
    ) -> list[tuple]:
        """Order (day, slot) as a slot-major round-robin: fill every day's
        morning before the afternoon, and fill all days before any day is
        overloaded — like a real college week.

        Packs sessions into the morning of every day first (slot 1 on the
        least-loaded day, then slot 1 on the next, ...), so a class shows a
        compact block of morning lectures with a single 1h lunch break, not a
        thin scatter with whole mornings empty beside the break. Days are
        cycled by their current load so no day fills up while others stay
        empty. Every candidate is still checked against the full hard checker —
        only the order changes.
        """
        group_day_load: dict[int, int] = defaultdict(int)
        for s in self.committed_slots:
            if s.student_group_id == session.student_group_id and s.day_of_week is not None:
                group_day_load[s.day_of_week] += 1

        # Least-loaded day first, then the *input* order as a tiebreak — the
        # input order is the seeded shuffle when generating variants, so
        # different seeds still yield diverse timetables (the diversity filter
        # needs that); unseeded, it is the plain Mon..Sat baseline.
        day_rank = {d: i for i, d in enumerate(working_days)}

        def key(item):
            day, (sn, _st, _en) = item
            return (group_day_load.get(day, 0), sn, day_rank.get(day, day))

        return sorted(
            ((d, st) for d in working_days for st in slot_times), key=key
        )

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
            break_slots=self._break_slots(),
        )
        sessions = self._build_sessions()
        # Lab practicals split into per-batch parallel sessions (DD-024). The
        # expansion is greedy-only: OR-Tools overrides solve() and keeps the
        # whole-division CP-SAT model.
        sessions = self._expand_lab_batches(sessions)
        working_days = self._get_working_days()
        slot_times = self._build_slot_times()
        slot_lookup = {sn: (st, en) for sn, st, en in slot_times}
        max_slot_number = max(slot_lookup)
        break_slots = self._break_slots()
        # The scan never proposes a break slot; it is a numbered non-teaching
        # row, not a candidate for placement.
        teachable_slot_times = [
            st for st in slot_times if st[0] not in break_slots
        ]
        # When seeded, randomise the search order so different seeds yield
        # different (still valid) timetables for the diversity filter.
        if self.rng is not None:
            working_days = list(working_days)
            teachable_slot_times = list(teachable_slot_times)
            self.rng.shuffle(working_days)
            self.rng.shuffle(teachable_slot_times)
        unscheduled: list[SessionToSchedule] = []

        # Parallel groups are the most constrained (they consume B rooms and
        # the whole division at once): place them before anything else, then
        # let any group that could not find a parallel window degrade to the
        # normal single-session path rather than being dropped.
        parallel_groups: dict = {}
        normal_sessions: list[SessionToSchedule] = []
        for session in sessions:
            if session.parallel_key is not None:
                parallel_groups.setdefault(session.parallel_key, []).append(session)
            else:
                normal_sessions.append(session)
        failed_groups: list[list] = []
        for group in parallel_groups.values():
            if not self._place_parallel_group(
                group, checker, working_days, teachable_slot_times,
                slot_lookup, max_slot_number,
            ):
                failed_groups.append(group)

        for session in normal_sessions + [
            member for group in failed_groups for member in group
        ]:
            placed = False
            rooms = self._get_rooms(session.room_requirements, session=session)
            if self.rng is not None:
                rooms = list(rooms)
                self.rng.shuffle(rooms)

            # The saturday_policy may forbid Saturday for this session type
            # even when Saturday is a declared working day.
            session_working_days = [
                d for d in working_days if self._day_allowed_for(d, session)
            ]
            if not session_working_days:
                unscheduled.append(session)
                continue

            # Order the (day, slot) scan. The gap criterion (variation) takes
            # precedence for seeded instances pursuing it; otherwise, when the
            # profile has active soft constraints, the scan leans toward those
            # preferences so the default greedy solver pursues them too.
            # Everything else spreads each class across the week (least-loaded
            # day first) instead of packing all sessions into the earliest days.
            scan = self._scan(session, session_working_days, teachable_slot_times)
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
                        batch_number=session.batch_number,
                        window_key=session.window_key,
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
                                batch_number=session.batch_number,
                                window_key=session.window_key,
                            ))
                        placed = True
                        break
            if not placed:
                unscheduled.append(session)

        if unscheduled:
            self.unplaced_count = len(unscheduled)
        return self.committed_slots
