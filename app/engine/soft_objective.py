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
