"""CP-SAT objective builders for soft constraints.

The greedy solver ignores soft preferences during placement (they are only
scored post-hoc to rank instances). OR-Tools can do better: every active soft
constraint that has an objective builder contributes a linear term to the
CP-SAT objective, so the solver actively *pursues* the college's preferences
instead of merely being ranked by them afterwards.

Placements stay strictly primary: each placed session carries a large fixed
weight (``PLACEMENT_WEIGHT``), so a soft preference can never trade away a
placed session — it only shapes which equal-cardinality solution the solver
returns. Weights are capped at ``DECIMAL(4, 2)`` (99.99) by the schema and the
soft terms are bounded by the placement count / slot count, so the base easily
dominates.

Mirrors ``scorer.py``: add a rule by writing a builder and registering it with
``@soft_objective("MY_TYPE")`` — no solver changes. A builder has the
signature::

    (ctx: ObjectiveContext, config: dict) -> list[tuple[expr, multiplier]]

returning ``(cp_model.LinearExpr, float)`` pairs that are added to the
objective as ``rule_weight * multiplier * expr``. Builders may add auxiliary
variables/constraints through ``ctx.model``.
"""
from __future__ import annotations

from typing import Callable

from ortools.sat.python import cp_model

# Base score a placed session contributes. Large enough that soft terms
# (max rule weight 99.99 x bounded magnitudes) can never out-weigh it.
PLACEMENT_WEIGHT = 1000.0

# type string -> objective builder
SOFT_OBJECTIVE_REGISTRY: dict[str, Callable] = {}


def soft_objective(constraint_type) -> Callable:
    """Register an objective builder for a soft constraint type."""
    key = getattr(constraint_type, "value", constraint_type)

    def deco(fn: Callable) -> Callable:
        SOFT_OBJECTIVE_REGISTRY[key] = fn
        return fn

    return deco


class ObjectiveContext:
    """Shared model access handed to every objective builder."""

    def __init__(self, model, x, sessions, slot_count):
        self.model = model
        # Decision variables: {(session_idx, day, slot, room_id): BoolVar}
        self.x = x
        self.sessions = sessions
        self.slot_count = slot_count


def build_soft_objective(model, x, sessions, soft_constraints, slot_count) -> list:
    """Return the list of ``(expr, weight)`` soft terms for the objective.

    Rules without a registered builder are skipped so future soft rules
    degrade gracefully — they still rank instances post-hoc via ``scorer.py``.
    """
    terms: list = []
    ctx = ObjectiveContext(model, x, sessions, slot_count)
    for rule in soft_constraints:
        if not getattr(rule, "is_active", True):
            continue
        rule_type = getattr(rule.constraint_type, "value", rule.constraint_type)
        builder = SOFT_OBJECTIVE_REGISTRY.get(rule_type)
        if builder is None:
            continue
        rule_weight = float(getattr(rule, "weight", 1.0) or 1.0)
        for expr, multiplier in builder(ctx, getattr(rule, "config_json", None)):
            # ``expr`` stays a bare int when a builder matches no variables.
            if isinstance(expr, int) and expr == 0:
                continue
            terms.append((expr, rule_weight * multiplier))
    return terms


# ── builders ───────────────────────────────────────────────

def _teacher_prefers_morning(ctx: ObjectiveContext, config) -> list:
    """Reward placing a teacher's sessions in the morning window.

    config: ``{"faculty_id"?: int, "boundary_slot"?: int}`` (default 4).
    Without ``faculty_id`` every teacher's sessions count. Mirrors the
    post-hoc scorer in ``scorer.py`` (a fraction is maximised by maximising
    the count of morning placements once the total count is fixed).
    """
    config = config or {}
    boundary = config.get("boundary_slot", 4)
    faculty_id = config.get("faculty_id")

    expr = 0
    for (si, _day, sn, _room), var in ctx.x.items():
        session = ctx.sessions[si]
        if faculty_id is not None and session.faculty_id != faculty_id:
            continue
        if sn <= boundary:
            expr += var
    return [(expr, 1.0)]


def _minimize_student_free_slots(ctx: ObjectiveContext, config) -> list:
    """Minimise the span of each student's day.

    For every (group, day) that gets at least one placement we model the
    first/last occupied slot and subtract ``last - first + 1``. Because placed
    sessions are already counted (primary objective), minimising the span is
    exactly minimising the free slots inside it — the same quantity the
    post-hoc scorer measures as ``1 - gaps / span``.
    """
    return _build_span_terms(ctx, "student_group_id", "compact")


def _minimize_teacher_free_slots(ctx: ObjectiveContext, config) -> list:
    """Minimise the span of each teacher's day (teacher-side mirror of
    :func:`_minimize_student_free_slots`)."""
    return _build_span_terms(ctx, "faculty_id", "compact_t")


def _avoid_consecutive_same_subject(ctx: ObjectiveContext, config) -> list:
    """Penalise back-to-back sessions of the same subject for the same group.

    For every (group, subject, day) that gets two adjacent placements we add a
    per-adjacent-pair penalty. The always-on ``SAME_SUBJECT_SAME_DAY``
    structural rule usually keeps a subject to one session per group per day,
    so this term is typically inert — it only bites when that structural rule
    is relaxed.
    """
    config = config or {}
    subject_id = config.get("subject_id")

    model, x, sessions = ctx.model, ctx.x, ctx.sessions
    by_group_subj_day: dict[tuple, list] = {}
    for (si, day, sn, _room), var in x.items():
        s = sessions[si]
        if s.subject_id is None or s.student_group_id is None:
            continue
        if subject_id is not None and s.subject_id != subject_id:
            continue
        by_group_subj_day.setdefault(
            (s.student_group_id, s.subject_id, day), []
        ).append((sn, var))

    terms: list = []
    for key, placements in by_group_subj_day.items():
        by_slot = {sn: v for sn, v in placements}
        day = key[2]
        for sn, var in placements:
            nxt = by_slot.get(sn + 1)
            if nxt is not None:
                pair = model.NewBoolVar(
                    f"adj_subj_{day}_{sn}"
                )
                model.Add(pair >= var + nxt - 1)
                terms.append((pair, -1.0))
    return terms


def _distribute_subjects_evenly(ctx: ObjectiveContext, config) -> list:
    """Reward placing a subject's sessions on distinct days.

    For each (group, subject) we count how many distinct days receive at least
    one session and reward that count, capped at the number of sessions (a
    subject fully spread over N days can score at most N). This mirrors the
    post-hoc scorer's ``distinct_days / sessions`` fraction.
    """
    config = config or {}
    subject_id = config.get("subject_id")

    model, x, sessions = ctx.model, ctx.x, ctx.sessions
    by_group_subj: dict[tuple, list] = {}
    for (si, day, _sn, _room), var in x.items():
        s = sessions[si]
        if s.subject_id is None or s.student_group_id is None:
            continue
        if subject_id is not None and s.subject_id != subject_id:
            continue
        by_group_subj.setdefault((s.student_group_id, s.subject_id), []).append(
            (day, var)
        )

    terms: list = []
    for (_gs, _), placements in by_group_subj.items():
        per_day: dict[int, list] = {}
        for day, var in placements:
            per_day.setdefault(day, []).append(var)
        for day, vs in per_day.items():
            # 1 if this day hosts at least one session of the subject.
            has = model.NewBoolVar(f"even_{day}")
            model.Add(has <= sum(vs))
            for var in vs:
                model.Add(has >= var)
            terms.append((has, 1.0))
    return terms


def _balance_teacher_load(ctx: ObjectiveContext, config) -> list:
    """Reward spreading each teacher's sessions evenly across days.

    Linear relaxation of the coefficient-of-variation objective: reward every
    (faculty, day) pair whose load stays at or below the teacher's daily mean
    (``sessions / working_days``), using a single quadratic-free approximation.
    A teacher packed onto one day cannot earn these "under-budget" bonuses,
    while a spread teacher can earn them for every day — which pushes CP-SAT
    toward the balanced solution without trading away placements.
    """
    config = config or {}
    faculty_id = config.get("faculty_id")

    model, x, sessions = ctx.model, ctx.x, ctx.sessions
    slot_count = ctx.slot_count
    by_fac_day: dict[tuple, list] = {}
    for (si, day, _sn, _room), var in x.items():
        s = sessions[si]
        if s.faculty_id is None:
            continue
        if faculty_id is not None and s.faculty_id != faculty_id:
            continue
        by_fac_day.setdefault((s.faculty_id, day), []).append(var)

    # total sessions per faculty (upper bound: slot_count per day is generous)
    by_fac: dict[int, list] = {}
    for (fid, day), vs in by_fac_day.items():
        by_fac.setdefault(fid, []).append((day, vs))
    if not by_fac:
        return []

    working_days = len(set(day for (fid, _day) in by_fac_day for fid in [fid]))
    terms: list = []
    for fid, day_vars in by_fac.items():
        all_vars = [v for _day, vs in day_vars for v in vs]
        total = model.NewIntVar(0, slot_count * 10, f"load_total_{fid}")
        model.Add(total == sum(all_vars))
        # daily budget = ceil(total / number of distinct days this teacher teaches)
        distinct_days = len(set(day for day, _vs in day_vars))
        budget = model.NewIntVar(0, slot_count * 10, f"load_budget_{fid}")
        model.Add(budget * distinct_days >= total)
        for _day, vs in day_vars:
            below = model.NewBoolVar(f"load_below_{fid}_{_day}")
            model.Add(below <= budget)
            model.Add(sum(vs) <= budget + slot_count * (1 - below))
            terms.append((below, 1.0))
    return terms


def _build_span_terms(ctx: ObjectiveContext, peer_attr: str, label: str) -> list:
    """One span-minimisation term per (peer, day) with ≥2 placements.

    ``peer_attr`` is the ``SessionToSchedule`` attribute to group by
    (``"student_group_id"`` or ``"faculty_id"``). A day with a single
    placement contributes nothing — it has no free slots. Returns
    ``(span, -1.0)`` pairs so the objective is *maximised* by packing.
    """
    model, x, sessions = ctx.model, ctx.x, ctx.sessions
    slot_count = ctx.slot_count

    by_peer_day: dict[tuple, list] = {}
    for (si, day, sn, _room), var in x.items():
        pid = getattr(sessions[si], peer_attr)
        by_peer_day.setdefault((pid, day), []).append((sn, var))

    terms: list = []
    for (pid, day), placements in by_peer_day.items():
        # A single placement has no gaps; anything more needs span modeling.
        if len(placements) < 2:
            continue
        has = model.NewBoolVar(f"{label}_has_{pid}_{day}")
        model.Add(has <= sum(v for _, v in placements))
        for _, var in placements:
            model.Add(has >= var)
        first = model.NewIntVar(1, slot_count, f"{label}_first_{pid}_{day}")
        last = model.NewIntVar(1, slot_count, f"{label}_last_{pid}_{day}")
        span = model.NewIntVar(0, slot_count, f"{label}_span_{pid}_{day}")
        for sn, var in placements:
            model.Add(first <= sn + slot_count * (1 - var))
            model.Add(last >= sn * var)
        # span == last - first + 1 when the peer-day is occupied, else 0.
        model.Add(span >= last - first + 1 - slot_count * (1 - has))
        model.Add(span <= slot_count * has)
        terms.append((span, -1.0))
    return terms


soft_objective("TEACHER_PREFERS_MORNING")(_teacher_prefers_morning)
soft_objective("MINIMIZE_STUDENT_FREE_SLOTS")(_minimize_student_free_slots)
soft_objective("MINIMIZE_TEACHER_FREE_SLOTS")(_minimize_teacher_free_slots)
soft_objective("AVOID_CONSECUTIVE_SAME_SUBJECT")(_avoid_consecutive_same_subject)
soft_objective("DISTRIBUTE_SUBJECTS_EVENLY")(_distribute_subjects_evenly)
soft_objective("BALANCE_TEACHER_LOAD")(_balance_teacher_load)
