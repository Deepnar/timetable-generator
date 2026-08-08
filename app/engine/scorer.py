"""Soft-constraint scorer.

Soft constraints don't fail a timetable — they rank it. Each scorer looks at a
finished instance's slots and returns a *satisfaction* value in ``[0.0, 1.0]``
(1.0 = fully satisfied). :func:`score_instance` combines them into one weighted
score in ``[0.0, 1.0]`` where **higher is better**; the scheduler stores it on
``instance.soft_score`` and records the best across instances on
``generation.score_best_instance``.

Mirrors the hard-constraint registry: add a rule by writing a scorer and
registering it with ``@soft_rule("MY_TYPE")`` — no scheduler changes.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Optional

from sqlalchemy.orm import Session

# type string -> scorer
SOFT_CONSTRAINT_REGISTRY: dict[str, Callable] = {}


def soft_rule(constraint_type) -> Callable:
    key = getattr(constraint_type, "value", constraint_type)

    def deco(fn: Callable) -> Callable:
        SOFT_CONSTRAINT_REGISTRY[key] = fn
        return fn

    return deco


class ScoringContext:
    """Shared lookups for scorers (kept for parity with the hard registry)."""

    def __init__(self, db: Session):
        self.db = db


def score_instance(slots, soft_constraints, ctx: ScoringContext) -> float:
    """Weighted mean of each active soft rule's satisfaction, in ``[0, 1]``.

    With no applicable rules the instance is treated as perfectly satisfied
    (1.0) so scoring never penalises a profile that defines no soft rules.
    """
    total_weight = 0.0
    acc = 0.0
    for rule in soft_constraints:
        if not getattr(rule, "is_active", True):
            continue
        rule_type = getattr(rule.constraint_type, "value", rule.constraint_type)
        scorer = SOFT_CONSTRAINT_REGISTRY.get(rule_type)
        if scorer is None:
            continue
        satisfaction = scorer(slots, getattr(rule, "config_json", None), ctx)
        weight = float(getattr(rule, "weight", 1.0) or 1.0)
        acc += weight * satisfaction
        total_weight += weight
    if total_weight == 0.0:
        return 1.0
    return round(acc / total_weight, 4)


# ── scorers ──────────────────────────────────────────────────

def _teacher_prefers_morning(slots, config, ctx) -> float:
    """Fraction of a teacher's sessions that fall in the morning window.

    config: ``{"faculty_id"?: int, "boundary_slot"?: int}`` (default boundary 4).
    Without ``faculty_id`` it scores every teacher's sessions together.
    """
    config = config or {}
    boundary = config.get("boundary_slot", 4)
    faculty_id = config.get("faculty_id")
    relevant = [
        s for s in slots
        if s.faculty_id is not None
        and (faculty_id is None or s.faculty_id == faculty_id)
    ]
    if not relevant:
        return 1.0
    good = sum(1 for s in relevant if s.slot_number <= boundary)
    return good / len(relevant)


def _minimize_student_free_slots(slots, config, ctx) -> float:
    """Reward compact student days (few gaps between first and last slot).

    Satisfaction = ``1 - gaps / occupied_span`` aggregated over every
    (group, day). A day with no holes scores 1.0.
    """
    by_group_day: dict[tuple, list[int]] = defaultdict(list)
    for s in slots:
        if s.student_group_id is not None and s.day_of_week is not None:
            by_group_day[(s.student_group_id, s.day_of_week)].append(s.slot_number)
    if not by_group_day:
        return 1.0

    total_span = 0
    total_gaps = 0
    for nums in by_group_day.values():
        span = max(nums) - min(nums) + 1
        total_span += span
        total_gaps += span - len(nums)
    if total_span == 0:
        return 1.0
    return 1.0 - (total_gaps / total_span)


def _minimize_teacher_free_slots(slots, config, ctx) -> float:
    """Reward compact teacher days (few gaps between first and last slot).

    The teacher-side mirror of :func:`_minimize_student_free_slots`: the span
    of every (faculty, day) the teacher actually teaches, with holes inside it
    counted as gaps. A day with no holes scores 1.0.
    """
    by_fac_day: dict[tuple, list[int]] = defaultdict(list)
    for s in slots:
        if s.faculty_id is not None and s.day_of_week is not None:
            by_fac_day[(s.faculty_id, s.day_of_week)].append(s.slot_number)
    if not by_fac_day:
        return 1.0

    total_span = 0
    total_gaps = 0
    for nums in by_fac_day.values():
        span = max(nums) - min(nums) + 1
        total_span += span
        total_gaps += span - len(nums)
    if total_span == 0:
        return 1.0
    return 1.0 - (total_gaps / total_span)


soft_rule("TEACHER_PREFERS_MORNING")(_teacher_prefers_morning)
soft_rule("MINIMIZE_STUDENT_FREE_SLOTS")(_minimize_student_free_slots)
soft_rule("MINIMIZE_TEACHER_FREE_SLOTS")(_minimize_teacher_free_slots)
