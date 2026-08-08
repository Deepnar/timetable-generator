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
from app.models.generation import TimetableSlot, VariationMode
from app.engine.constraint_checker import ConstraintChecker, SlotCandidate
from app.engine.solvers.greedy_solver import GreedySolver
from app.engine.soft_objective import (
    PLACEMENT_WEIGHT,
    ObjectiveContext,
    build_soft_objective,
    _minimize_teacher_free_slots,
    _minimize_student_free_slots,
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
        max_slot_number = max(slot_lookup)
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
                for sn, _st, _en in slot_times:
                    end_slot = sn + session.block_length - 1
                    if end_slot > max_slot_number:
                        continue
                    for room in rooms:
                        candidate = SlotCandidate(
                            instance_id=self.instance_id, day_of_week=day,
                            slot_number=sn, start_time=slot_lookup[sn][0],
                            end_time=slot_lookup[end_slot][1],
                            faculty_id=session.faculty_id, room_id=room.id,
                            student_group_id=session.student_group_id,
                            subject_id=session.subject_id,
                            session_type=session.session_type,
                            slot_date=self._materialize_slot_date(day),
                            is_cross_department=session.is_cross_department,
                            block_length=session.block_length,
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

        # Relational constraints. A block session registers one variable for
        # every slot it occupies, so no teacher/room/group can overlap any part
        # of it; the daily/weekly load buckets count the block's full length.
        by_teacher_slot = defaultdict(list)
        by_room_slot = defaultdict(list)
        by_group_slot = defaultdict(list)
        by_group_subject_day = defaultdict(list)
        by_teacher_day = defaultdict(list)
        by_teacher = defaultdict(list)
        for (si, day, sn, room_id), var in x.items():
            s = sessions[si]
            for n in range(sn, sn + s.block_length):
                by_teacher_slot[(s.faculty_id, day, n)].append(var)
                by_room_slot[(room_id, day, n)].append(var)
                by_group_slot[(s.student_group_id, day, n)].append(var)
            by_group_subject_day[(s.student_group_id, s.subject_id, day)].append(var)
            for _ in range(s.block_length):
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

        self._add_exam_separation(model, x, sessions)

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
        # Instance variation: for a seeded instance pursuing a gap criterion,
        # add a small secondary objective term (teacher-gap / student-gap) so
        # the re-rolled candidate is not just a random seed — it actively packs
        # the requested peer's sessions. The weights stay far below
        # PLACEMENT_WEIGHT so a placed session is never traded away.
        for expr, weight in self._build_variation_terms(
            model, x, sessions, len(slot_times)
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
            end_slot = sn + s.block_length - 1
            st = slot_lookup[sn][0]
            en = slot_lookup[end_slot][1]
            candidate = SlotCandidate(
                instance_id=self.instance_id, day_of_week=day, slot_number=sn,
                start_time=st, end_time=en, faculty_id=s.faculty_id,
                room_id=room_id, student_group_id=s.student_group_id,
                subject_id=s.subject_id, session_type=s.session_type,
                slot_date=self._materialize_slot_date(day),
                is_cross_department=s.is_cross_department,
                block_length=s.block_length,
            )
            if checker.is_valid(candidate):
                slot_date = self._materialize_slot_date(day)
                for n in range(sn, end_slot + 1):
                    n_st, n_en = slot_lookup[n]
                    self.committed_slots.append(TimetableSlot(
                        instance_id=self.instance_id, day_of_week=day,
                        slot_number=n, start_time=n_st, end_time=n_en,
                        faculty_id=s.faculty_id, room_id=room_id,
                        student_group_id=s.student_group_id,
                        subject_id=s.subject_id, session_type=s.session_type,
                        slot_date=slot_date, is_manual_override=False,
                    ))
        return self.committed_slots

    def _faculty(self, faculty_id):
        if not hasattr(self, "_fac_cache"):
            self._fac_cache: dict = {}
        if faculty_id not in self._fac_cache:
            self._fac_cache[faculty_id] = self.db.get(Faculty, faculty_id)
        return self._fac_cache[faculty_id]

    def _add_exam_separation(self, model, x, sessions):
        """Model EXAM_DATE_SEPARATION as a relational CP-SAT rule.

        The registry validator reads committed slots, so it cannot fire during
        the static domain-pruning pass (the committed set is empty there) and
        would only be caught by the final pass — which would *drop* placements,
        letting CP-SAT pack a group's exams onto one day and shed the rest. To
        avoid that, the rule is also modelled here directly: for each group,
        at most one exam per calendar date, and no exam on two dates closer
        than ``min_days``. Without a ``term_start`` anchor the dates are
        unknown and the rule stays inert, matching the validator.
        """
        exam_sep: int | None = None
        for rule in self._load_hard_constraints():
            rule_type = getattr(rule.constraint_type, "value", rule.constraint_type)
            if rule_type != "EXAM_DATE_SEPARATION":
                continue
            min_days = (getattr(rule, "config_json", None) or {}).get("min_days")
            if min_days:
                exam_sep = int(min_days)
                break
        if not exam_sep:
            return

        by_group_date: dict[int, dict] = defaultdict(lambda: defaultdict(list))
        for (si, day, _sn, _room_id), var in x.items():
            d = self._materialize_slot_date(day)
            if d is not None:
                by_group_date[sessions[si].student_group_id][d].append(var)
        for by_date in by_group_date.values():
            for vs in by_date.values():
                model.Add(sum(vs) <= 1)  # one exam per group per date
            dates = sorted(by_date)
            for i in range(len(dates)):
                for j in range(i + 1, len(dates)):
                    if (dates[j] - dates[i]).days < exam_sep:
                        model.Add(sum(by_date[dates[i]]) + sum(by_date[dates[j]]) <= 1)

    def _load_soft_constraints(self) -> list[SoftConstraint]:
        """Active soft rules for the resolved profile (global + per-member)."""
        return list(self.profile.soft_constraints)

    def _build_variation_terms(self, model, x, sessions, slot_count) -> list:
        """Secondary objective terms for a gap-minimising variation.

        Only seeded instances pursue the criterion — instance #1 stays the
        deterministic baseline unless ``variation="best"`` is requested (and
        ``"best"`` itself is handled by the scheduler keeping the best-scoring
        attempt, not by an extra objective term here). The builders return
        ``(span, -1.0)`` pairs, so each placed term subtracts a peer's daily
        span and the solver is pushed to pack sessions of the same teacher or
        group into contiguous slots.
        """
        if self.seed is None:
            return []
        ctx = ObjectiveContext(model, x, sessions, slot_count)
        if self.variation == VariationMode.MINIMIZE_TEACHER_GAPS:
            return _minimize_teacher_free_slots(ctx, {})
        if self.variation == VariationMode.MINIMIZE_STUDENT_GAPS:
            return _minimize_student_free_slots(ctx, {})
        return []
