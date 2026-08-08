"""OR-Tools CP-SAT solver.

An exact constraint solver offered as an alternative to the greedy heuristic
(select ``algorithm="OR_TOOLS"`` on ``POST /generate``). It reuses
``GreedySolver``'s problem building — sessions, the slot grid, rooms, profile
params and feature flags — and expresses the placement as a CP-SAT model whose
objective maximises the number of placed sessions.

Constraint handling is split to match how the ``ConstraintChecker`` works:

* **Per-candidate ("static") rules** — capacity, room type, teacher
  availability, recurring blackouts, cross-timetable reservations, and the
  data-driven registry rules (``SUBJECT_TIME_PREFERENCE`` etc.) — are enforced
  by *pruning the variable domain*: a variable is only created for a
  (session, day, slot, room) the checker accepts against an empty timetable.
* **Relational rules** — no teacher/room/group double-book, one subject per
  group per day, faculty daily/weekly load — are added as CP-SAT constraints.

A final pass through the full checker guarantees validity even for
committed-dependent registry rules (e.g. ``MAX_CONSECUTIVE_SAME_TEACHER``),
which CP-SAT does not model; such a rule can only *drop* a placement, never
produce an invalid one.
"""
from collections import defaultdict

from app.models.faculty import Faculty
from app.models.constraints import SoftConstraint
from app.models.generation import TimetableSlot
from app.engine.constraint_checker import ConstraintChecker, SlotCandidate
from app.engine.solvers.greedy_solver import GreedySolver
from app.engine.soft_objective import (
    PLACEMENT_WEIGHT,
    build_soft_objective,
)


class ORToolsSolver(GreedySolver):
    """CP-SAT placement. Same public interface as :class:`GreedySolver`."""

    max_time_seconds = 5.0

    def solve(self) -> list[TimetableSlot]:
        from ortools.sat.python import cp_model  # local import; heavy dependency

        sessions = self._build_sessions()
        if not sessions:
            return self.committed_slots

        working_days = self._get_working_days()
        slot_times = self._build_slot_times()
        slot_lookup = {sn: (st, en) for sn, st, en in slot_times}
        hard_constraints = self._load_hard_constraints()

        # Domain pruning uses the same checker as greedy with an EMPTY committed
        # set, so only per-candidate ("static") rules fire — including registry
        # rules like SUBJECT_TIME_PREFERENCE and LAB_BATCH_ROTATION.
        static_checker = ConstraintChecker(
            self.db, [], settings=self.settings,
            reserved=self.reserved_conflicts,
            hard_constraints=hard_constraints,
        )

        model = cp_model.CpModel()
        x: dict[tuple, object] = {}
        for si, session in enumerate(sessions):
            rooms = self._get_rooms(session.requires_lab)
            for day in working_days:
                for sn, st, en in slot_times:
                    for room in rooms:
                        candidate = SlotCandidate(
                            instance_id=self.instance_id, day_of_week=day,
                            slot_number=sn, start_time=st, end_time=en,
                            faculty_id=session.faculty_id, room_id=room.id,
                            student_group_id=session.student_group_id,
                            subject_id=session.subject_id,
                            session_type=session.session_type,
                            slot_date=self._materialize_slot_date(day),
                            is_cross_department=session.is_cross_department,
                        )
                        if not static_checker.is_valid(candidate):
                            continue
                        x[(si, day, sn, room.id)] = model.NewBoolVar(
                            f"x_{si}_{day}_{sn}_{room.id}"
                        )

        # Each session placed at most once (unplaced degrades gracefully).
        per_session: dict[int, list] = defaultdict(list)
        for (si, _d, _s, _r), var in x.items():
            per_session[si].append(var)
        for vs in per_session.values():
            model.Add(sum(vs) <= 1)

        # Relational constraints.
        by_teacher_slot = defaultdict(list)
        by_room_slot = defaultdict(list)
        by_group_slot = defaultdict(list)
        by_group_subject_day = defaultdict(list)
        by_teacher_day = defaultdict(list)
        by_teacher = defaultdict(list)
        for (si, day, sn, room_id), var in x.items():
            s = sessions[si]
            by_teacher_slot[(s.faculty_id, day, sn)].append(var)
            by_room_slot[(room_id, day, sn)].append(var)
            by_group_slot[(s.student_group_id, day, sn)].append(var)
            by_group_subject_day[(s.student_group_id, s.subject_id, day)].append(var)
            by_teacher_day[(s.faculty_id, day)].append(var)
            by_teacher[s.faculty_id].append(var)

        for vs in by_teacher_slot.values():
            model.Add(sum(vs) <= 1)
        for vs in by_room_slot.values():
            model.Add(sum(vs) <= 1)
        for vs in by_group_slot.values():
            model.Add(sum(vs) <= 1)
        for vs in by_group_subject_day.values():
            model.Add(sum(vs) <= 1)

        for (fid, _day), vs in by_teacher_day.items():
            fac = self._faculty(fid)
            if fac and fac.max_hours_per_day:
                model.Add(sum(vs) <= fac.max_hours_per_day)
        for fid, vs in by_teacher.items():
            fac = self._faculty(fid)
            if fac and fac.max_hours_per_week:
                model.Add(sum(vs) <= fac.max_hours_per_week)

        # Soft preferences (gated by the college scoring flag): fold active
        # soft constraints into the objective so the solver pursues them,
        # not just the placement count. Placements stay strictly primary via
        # PLACEMENT_WEIGHT; the soft terms only break ties among solutions
        # with the same number of placements.
        objective = PLACEMENT_WEIGHT * sum(x.values())
        if self.settings.enable_soft_constraint_scoring:
            for expr, weight in build_soft_objective(
                model, x, sessions, self._load_soft_constraints(), len(slot_times)
            ):
                objective += weight * expr
        model.Maximize(objective)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.max_time_seconds
        # A seed varies which optimal assignment is returned (diversity filter).
        if self.seed is not None:
            solver.parameters.random_seed = self.seed
            solver.parameters.randomize_search = True
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self.committed_slots

        chosen = sorted(k for k, var in x.items() if solver.Value(var) == 1)

        # Safety net: validate against the full checker (now committed-aware),
        # so committed-dependent registry rules are also respected.
        checker = ConstraintChecker(
            self.db, self.committed_slots, settings=self.settings,
            reserved=self.reserved_conflicts, hard_constraints=hard_constraints,
        )
        for si, day, sn, room_id in chosen:
            s = sessions[si]
            st, en = slot_lookup[sn]
            candidate = SlotCandidate(
                instance_id=self.instance_id, day_of_week=day, slot_number=sn,
                start_time=st, end_time=en, faculty_id=s.faculty_id,
                room_id=room_id, student_group_id=s.student_group_id,
                subject_id=s.subject_id, session_type=s.session_type,
                slot_date=self._materialize_slot_date(day),
                is_cross_department=s.is_cross_department,
            )
            if checker.is_valid(candidate):
                self.committed_slots.append(TimetableSlot(
                    instance_id=self.instance_id, day_of_week=day, slot_number=sn,
                    start_time=st, end_time=en, faculty_id=s.faculty_id,
                    room_id=room_id, student_group_id=s.student_group_id,
                    subject_id=s.subject_id, session_type=s.session_type,
                    slot_date=self._materialize_slot_date(day),
                    is_manual_override=False,
                ))
        return self.committed_slots

    def _faculty(self, faculty_id):
        if not hasattr(self, "_fac_cache"):
            self._fac_cache: dict = {}
        if faculty_id not in self._fac_cache:
            self._fac_cache[faculty_id] = self.db.get(Faculty, faculty_id)
        return self._fac_cache[faculty_id]

    def _load_soft_constraints(self) -> list[SoftConstraint]:
        """Active soft rules for the resolved profile (global + per-member)."""
        return list(self.profile.soft_constraints)
