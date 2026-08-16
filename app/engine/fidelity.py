"""Fidelity scorer (Phase 5, A8): "is a generated timetable good?" as numbers.

The 46 real TCET timetables are a labelled dataset. These functions score a
generated (or published) timetable against them and against the college's own
declared rules, so "the timetables aren't that good" stops being a feeling.

Metrics (audit A8):

- ``hours_deltas`` — weekly hours per (subject, division) vs the published
  grid, within ±1. The Phase 3 exit metric.
- ``break_slot_violations`` / ``saturday_violations`` — sessions placed in a
  declared break slot / on a Saturday under ``saturday_policy=NONE``.
- ``room_stability`` — fraction of a division's non-lab sessions in its
  venue (home rooms).
- ``teachers_per_subject_group`` — distinct teachers per (subject, division);
  1 is the target, more means the rotation has drifted.
- ``faculty_utilisation`` — demanded vs available faculty hours per
  department.
- ``batch_coverage`` — whether every lab batch receives every lab subject
  exactly once (the constructed rotation, A1).

The scorer is pure: the grid side reads ``info/import/timetables.json``, the
placed side reads the DB. Golden tests regenerate every division and assert
these metrics do not regress (Phase 5).
"""
from __future__ import annotations

from collections import defaultdict


def grid_hours(timetables: list[dict]) -> dict[tuple[str, str], int]:
    """Weekly hours per (group_name, subject_code) from the published grids.

    Counts LECTURE/TUTORIAL/ACTIVITY cells (labs are batch rows and count
    through the window model, not the grid-cell count).
    """
    hours: dict[tuple[str, str], int] = defaultdict(int)
    for t in timetables:
        for c in t["cells"]:
            k = c.get("kind")
            if k in ("LECTURE", "TUTORIAL", "ACTIVITY") and c.get("subject"):
                hours[(t["group_name"], c["subject"])] += 1
    return dict(hours)


def assignment_hours(db, *, group_ids: list[int] | None = None,
                     subject_ids: list[int] | None = None
                     ) -> dict[tuple[str, str], int]:
    """Weekly hours per (group_name, subject_name) from assignment rows.

    Non-batched rows only (lab windows are batch rows; their hours are
    window-level, not per-division weekly load).
    """
    from sqlalchemy import select
    from app.models.subject_assignments import SubjectAssignment
    from app.models.groups import StudentGroup
    from app.models.subjects import Subject

    hours: dict[tuple[str, str], int] = defaultdict(int)
    q = select(SubjectAssignment).where(SubjectAssignment.batch_number.is_(None))
    if group_ids:
        q = q.where(SubjectAssignment.group_id.in_(group_ids))
    if subject_ids:
        q = q.where(SubjectAssignment.subject_id.in_(subject_ids))
    for a in db.scalars(q).all():
        g = db.get(StudentGroup, a.group_id)
        s = db.get(Subject, a.subject_id)
        if g and s:
            hours[(g.name, s.name)] += a.weekly_hours or 0
    return dict(hours)


def grid_gap_subjects(timetables: list[dict]) -> set[tuple[str, str]]:
    """(group, subject) pairs whose grid cells name NO faculty at all.

    The college's grid lists a subject (PROJECT, online electives like AAD)
    without a teacher, so no assignment can exist and the registrar must
    supply one — the solver cannot be blamed for a gap the input declares.
    """
    gaps: set[tuple[str, str]] = set()
    for t in timetables:
        by_subject: dict[str, list[dict]] = defaultdict(list)
        for c in t["cells"]:
            k = c.get("kind")
            if k in ("LECTURE", "TUTORIAL", "ACTIVITY") and c.get("subject"):
                by_subject[c["subject"]].append(c)
        for code, cells in by_subject.items():
            if all(not (c.get("faculty") or []) for c in cells):
                gaps.add((t["group_name"], code))
    return gaps


def hours_deltas(db, timetables: list[dict],
                 code_to_name: dict[tuple, str] | None = None,
                 tolerance: int = 1) -> tuple[list[tuple], int]:
    """(subject, division) pairs whose hours deviate beyond ``tolerance``.

    ``code_to_name`` maps (department_code, semester, subject_code) -> name;
    when omitted the codes are compared directly against assignment names.

    Returns (bad_pairs, total_pairs); each bad pair is
    ``(group, name, grid_hours, assignment_hours)``.
    """
    grid = grid_hours(timetables)
    assigns = assignment_hours(db)
    bad: list[tuple] = []
    seen: set[tuple] = set()
    total = 0
    for t in timetables:
        sem, dept = t["semester"], t["group_name"].split("-")[0]
        for (gname, code), grid_h in sorted(grid.items()):
            if gname != t["group_name"]:
                continue
            name = code_to_name.get((dept, sem, code), code) if code_to_name else code
            key = (gname, name)
            if key in seen:
                continue
            seen.add(key)
            total += 1
            got = assigns.get(key, 0)
            if abs(grid_h - got) > tolerance:
                bad.append((gname, name, grid_h, got))
    return bad, total


def break_slot_violations(db, instance_id: int,
                          break_slots: set[int],
                          slots: list | None = None) -> int:
    """Sessions placed in a declared break slot of the instance."""
    if slots is None:
        from sqlalchemy import select
        from app.models.generation import TimetableSlot
        slots = db.scalars(
            select(TimetableSlot).where(TimetableSlot.instance_id == instance_id)
        ).all()
    return sum(1 for s in slots if s.slot_number in break_slots)


def saturday_violations(db, instance_id: int,
                        policy: str = "NONE",
                        slots: list | None = None) -> int:
    """Sessions placed on Saturday under a given saturday_policy.

    ``NONE``: every Saturday session is a violation. ``ACTIVITY_ONLY``: only
    non-activity sessions. ``FULL``: none.
    """
    if slots is None:
        from sqlalchemy import select
        from app.models.generation import TimetableSlot
        slots = db.scalars(
            select(TimetableSlot).where(TimetableSlot.instance_id == instance_id)
        ).all()
    policy = (policy or "NONE").upper()
    if policy == "FULL":
        return 0
    count = 0
    for s in slots:
        if s.day_of_week != 5:
            continue
        stype = getattr(s.session_type, "value", s.session_type)
        if policy == "ACTIVITY_ONLY" and stype in ("IP", "ACTIVITY", "CUSTOM",
                                                   "SEMINAR", "EVENT"):
            continue
        count += 1
    return count


def room_stability(db, instance_id: int, slots: list | None = None) -> float:
    """Fraction of non-lab sessions in the division's venue (home rooms).

    1.0 means every lecture stayed in the college's own room. None when the
    instance has no non-lab sessions or no home rooms.
    """
    if slots is None:
        from sqlalchemy import select
        from app.models.generation import TimetableSlot
        slots = db.scalars(
            select(TimetableSlot).where(TimetableSlot.instance_id == instance_id)
        ).all()
    from app.models.groups import StudentGroup

    non_lab = [s for s in slots
               if str(getattr(s.session_type, "value", s.session_type)).upper()
               != "LAB"]
    if not non_lab:
        return None
    home_ids: set[int] = set()
    for s in non_lab:
        g = db.get(StudentGroup, s.student_group_id) if s.student_group_id else None
        if g is None:
            continue
        home_ids |= {g.home_room_id, g.home_room_secondary_id}
    home_ids = {i for i in home_ids if i is not None}
    if not home_ids:
        return None
    in_home = sum(1 for s in non_lab if s.room_id in home_ids)
    return in_home / len(non_lab)


def teachers_per_subject_group(db, *, group_ids: list[int] | None = None
                               ) -> dict[tuple[str, str], int]:
    """Distinct teachers per (subject, division) for NON-batch rows.

    The 1-teacher target applies to lectures: a subject should be taught by
    one teacher. Lab windows are excluded — the batch rotation deliberately
    spreads each practical across several teachers (A1).
    """
    from sqlalchemy import select
    from app.models.subject_assignments import SubjectAssignment
    from app.models.groups import StudentGroup
    from app.models.subjects import Subject

    q = select(SubjectAssignment).where(
        SubjectAssignment.faculty_id.isnot(None),
        SubjectAssignment.batch_number.is_(None))
    if group_ids:
        q = q.where(SubjectAssignment.group_id.in_(group_ids))
    out: dict[tuple[str, str], set[int]] = defaultdict(set)
    for a in db.scalars(q).all():
        g = db.get(StudentGroup, a.group_id)
        s = db.get(Subject, a.subject_id)
        if g and s:
            out[(g.name, s.name)].add(a.faculty_id)
    return {k: len(v) for k, v in out.items()}


def faculty_utilisation(db) -> dict[str, dict]:
    """Demanded vs available faculty hours per department.

    Demand = sum of assignment weekly_hours; available = sum of
    max_hours_per_week over faculty with a cap set.
    """
    from sqlalchemy import select, func
    from app.models.subject_assignments import SubjectAssignment
    from app.models.faculty import Faculty

    demand: dict[str, int] = defaultdict(int)
    faculty_by_id: dict[int, object] = {}
    for a in db.scalars(select(SubjectAssignment)).all():
        if a.faculty_id is None:
            continue
        demand[a.faculty_id] += a.weekly_hours or 1
    available: dict[str, int] = defaultdict(int)
    dept_of: dict[int, str] = {}
    for f in db.scalars(select(Faculty)).all():
        dept_of[f.id] = f.department or "?"
        if f.max_hours_per_week:
            available[dept_of[f.id]] += f.max_hours_per_week
    out = {}
    for fid, hrs in demand.items():
        dept = dept_of.get(fid, "?")
        d = out.setdefault(dept, {"demand": 0, "capacity": 0})
        d["demand"] += hrs
        d["capacity"] = available.get(dept, 0)
    for dept, d in out.items():
        d["utilisation"] = (d["demand"] / d["capacity"]
                            if d["capacity"] else None)
    return out


def batch_coverage(db, *, group_ids: list[int] | None = None
                   ) -> dict[str, list]:
    """Lab batch coverage per division: every batch, every lab subject.

    A lab subject is covered when every batch of the division has an
    assignment row for it (the constructed rotation, A1). Returns a dict of
    division -> list of missing (batch, subject) pairs (empty = complete).
    """
    from sqlalchemy import select
    from app.models.subject_assignments import SubjectAssignment
    from app.models.groups import StudentGroup
    from app.models.subjects import Subject

    q = select(SubjectAssignment).where(SubjectAssignment.batch_number.isnot(None))
    if group_ids:
        q = q.where(SubjectAssignment.group_id.in_(group_ids))
    rows = db.scalars(q).all()
    per_group: dict[int, list] = defaultdict(list)
    for a in rows:
        per_group[a.group_id].append(a)
    out: dict[str, list] = {}
    for gid, rs in per_group.items():
        g = db.get(StudentGroup, gid)
        if g is None:
            continue
        batches = {r.batch_number for r in rs}
        lab_subjects = {
            db.get(Subject, r.subject_id).name
            for r in rs
            if r.subject_id and db.get(Subject, r.subject_id)
        }
        missing = []
        for subj in sorted(lab_subjects):
            for b in sorted(batches):
                if not any(r.batch_number == b
                           and db.get(Subject, r.subject_id) is not None
                           and db.get(Subject, r.subject_id).name == subj
                           for r in rs):
                    missing.append((b, subj))
        out[g.name] = missing
    return out
