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


def _avoid_consecutive_same_subject(slots, config, ctx) -> float:
    """Reward not placing the same subject back-to-back for the same group.

    config: ``{"subject_id"?: int}`` (default: every subject). Satisfaction is
    the fraction of (group, subject, day) runs that avoid adjacent same-subject
    sessions. With the always-on ``SAME_SUBJECT_SAME_DAY`` structural rule a
    subject appears at most once per group per day, so this is usually 1.0 —
    the rule exists for colleges that relax that structural behaviour.
    """
    config = config or {}
    subject_id = config.get("subject_id")

    # slot_number -> adjacent pairs in a consecutive block
    def adjacent_pairs(nums):
        return sum(1 for a, b in zip(sorted(nums), sorted(nums)[1:]) if b == a + 1)

    by_group_subject_day: dict[tuple, list[int]] = defaultdict(list)
    for s in slots:
        if (s.subject_id is None or s.student_group_id is None
                or s.day_of_week is None):
            continue
        if subject_id is not None and s.subject_id != subject_id:
            continue
        by_group_subject_day[(s.student_group_id, s.subject_id,
                              s.day_of_week)].append(s.slot_number)
    if not by_group_subject_day:
        return 1.0

    total_adjacent = 0
    total_sessions = 0
    for nums in by_group_subject_day.values():
        total_adjacent += adjacent_pairs(nums)
        total_sessions += len(nums)
    if total_sessions == 0:
        return 1.0
    # Max possible adjacent pairs ≈ sessions (fully contiguous).
    return 1.0 - (total_adjacent / total_sessions)


def _distribute_subjects_evenly(slots, config, ctx) -> float:
    """Reward spreading a subject's sessions across distinct weekdays.

    config: ``{"subject_id"?: int}``. For each (group, subject) measure the
    number of distinct days its sessions land on, normalised by the number of
    sessions (a subject with N sessions spread over N days scores 1.0). This
    pushes sessions onto different days rather than clustering them.
    """
    config = config or {}
    subject_id = config.get("subject_id")

    by_group_subject: dict[tuple, set[int]] = defaultdict(set)
    session_counts: dict[tuple, int] = defaultdict(int)
    for s in slots:
        if (s.subject_id is None or s.student_group_id is None
                or s.day_of_week is None):
            continue
        if subject_id is not None and s.subject_id != subject_id:
            continue
        by_group_subject[(s.student_group_id, s.subject_id)].add(s.day_of_week)
        session_counts[(s.student_group_id, s.subject_id)] += 1
    if not by_group_subject:
        return 1.0

    total = 0.0
    for key, days in by_group_subject.items():
        n = session_counts[key]
        if n <= 1:
            total += 1.0
            continue
        total += len(days) / n
    return total / len(by_group_subject)


def _balance_teacher_load(slots, config, ctx) -> float:
    """Reward an even spread of each teacher's load across the week.

    config: ``{"faculty_id"?: int}``. For each teacher measures how evenly
    their per-day session counts sit around their own average, scored as
    ``1 - coefficient_of_variation``. A teacher with 2/2/2/2 across four days
    scores 1.0; one with 8/0/0/0 scores ~0.
    """
    config = config or {}
    faculty_id = config.get("faculty_id")

    by_fac_day: dict[tuple, int] = defaultdict(int)
    for s in slots:
        if s.faculty_id is None or s.day_of_week is None:
            continue
        if faculty_id is not None and s.faculty_id != faculty_id:
            continue
        by_fac_day[(s.faculty_id, s.day_of_week)] += 1
    if not by_fac_day:
        return 1.0

    per_fac: dict[int, list[int]] = defaultdict(list)
    for (fid, _day), n in by_fac_day.items():
        per_fac[fid].append(n)

    total = 0.0
    for nums in per_fac.values():
        mean = sum(nums) / len(nums)
        if mean == 0:
            total += 1.0
            continue
        var = sum((n - mean) ** 2 for n in nums) / len(nums)
        cv = (var ** 0.5) / mean
        total += max(0.0, 1.0 - cv)
    return total / len(per_fac)


soft_rule("TEACHER_PREFERS_MORNING")(_teacher_prefers_morning)
soft_rule("MINIMIZE_STUDENT_FREE_SLOTS")(_minimize_student_free_slots)
soft_rule("MINIMIZE_TEACHER_FREE_SLOTS")(_minimize_teacher_free_slots)
soft_rule("AVOID_CONSECUTIVE_SAME_SUBJECT")(_avoid_consecutive_same_subject)
soft_rule("DISTRIBUTE_SUBJECTS_EVENLY")(_distribute_subjects_evenly)
soft_rule("BALANCE_TEACHER_LOAD")(_balance_teacher_load)
