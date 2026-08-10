"""Audit generated instances for real conflicts / quality issues.

Checks the committed slots of every generated instance for:
- faculty double-booked in the same (day, slot)
- room double-booked in the same (day, slot)
- group double-booked in the same (day, slot)
- same subject + group on the same day (SAME_SUBJECT_SAME_DAY)
- faculty weekly load over cap
- room capacity below group strength
- duplicate slots (same subject/faculty/group/room/day/slot repeated)

Usage:
    uv run python -m scripts.audit_instances [--run-id N]
    (no arg: audit the most recent run)
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict

from sqlalchemy import select

from app.database import SessionLocal
from app.models.generation import (
    TimetableGeneration, TimetableInstance, TimetableSlot,
    GenerationStatus, InstanceStatus,
)


def audit(slots: list[TimetableSlot], db) -> dict:
    issues: dict[str, list] = {
        "faculty_double_book": [],
        "room_double_book": [],
        "group_double_book": [],
        "same_subject_group_day": [],
        "faculty_over_weekly_cap": [],
        "room_capacity_under_strength": [],
        "duplicate_slots": [],
    }

    from app.models.faculty import Faculty
    from app.models.rooms import Room
    from app.models.groups import StudentGroup
    from app.models.subjects import Subject

    fac = {f.id: f for f in db.scalars(select(Faculty))}
    rooms = {r.id: r for r in db.scalars(select(Room))}
    groups = {g.id: g for g in db.scalars(select(StudentGroup))}
    subjects = {s.id: s for s in db.scalars(select(Subject))}

    key = lambda s: (s.day_of_week, s.slot_number) if s.slot_number is not None else None
    fk = defaultdict(list)
    rk = defaultdict(list)
    gk = defaultdict(list)
    sgk = defaultdict(list)
    fac_load = Counter()
    dups = Counter()

    for s in slots:
        k = key(s)
        if k is None:
            continue
        if s.faculty_id is not None:
            fk[(s.faculty_id, *k)].append(s)
            fac_load[s.faculty_id] += 1
        if s.room_id is not None:
            rk[(s.room_id, *k)].append(s)
        if s.student_group_id is not None:
            gk[(s.student_group_id, *k)].append(s)
            if s.subject_id is not None:
                sgk[(s.student_group_id, s.subject_id, k[0])].append(s)
        dups[(s.subject_id, s.faculty_id, s.room_id, s.student_group_id,
              s.day_of_week, s.slot_number)] += 1

    for (fid, d, sn), ss in fk.items():
        if len(ss) > 1:
            issues["faculty_double_book"].append(
                f"faculty {fac.get(fid).name if fid in fac else fid} "
                f"day={d} slot={sn} x{len(ss)}")
    for (rid, d, sn), ss in rk.items():
        if len(ss) > 1:
            issues["room_double_book"].append(
                f"room {rooms.get(rid).name if rid in rooms else rid} "
                f"day={d} slot={sn} x{len(ss)}")
    for (gid, d, sn), ss in gk.items():
        if len(ss) > 1:
            issues["group_double_book"].append(
                f"group {groups.get(gid).name if gid in groups else gid} "
                f"day={d} slot={sn} x{len(ss)}")
    for (gid, subj, d), ss in sgk.items():
        if len(ss) > 1:
            issues["same_subject_group_day"].append(
                f"subject '{subjects.get(subj).name if subj in subjects else subj}' "
                f"taught twice to group '{groups.get(gid).name if gid in groups else gid}' "
                f"on day {d}")
    for fid, n in fac_load.items():
        cap = fac[fid].max_hours_per_week if fid in fac else 20
        if n > cap:
            issues["faculty_over_weekly_cap"].append(
                f"faculty '{fac.get(fid).name if fid in fac else fid}' "
                f"{n} sessions > cap {cap}")
    for s in slots:
        if s.room_id is not None and s.student_group_id is not None:
            r = rooms.get(s.room_id)
            g = groups.get(s.student_group_id)
            if r and g and r.capacity < g.strength:
                issues["room_capacity_under_strength"].append(
                    f"room {r.name} cap {r.capacity} < group {g.name} strength {g.strength}")
    for k, n in dups.items():
        if n > 1:
            issues["duplicate_slots"].append(f"{k} x{n}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, default=None,
                        help="audit a specific run (default: latest)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        gen_q = select(TimetableGeneration)
        if args.run_id is not None:
            gen_q = gen_q.where(TimetableGeneration.id == args.run_id)
        gen = db.scalars(gen_q.order_by(TimetableGeneration.id.desc())).first()
        if gen is None:
            print("no generation run found")
            return 1
        print(f"run #{gen.id}: {gen.generation_status.value} "
              f"algorithm={gen.algorithm_used.value} "
              f"variation={gen.variation.value} dur_ms={gen.run_duration_ms}")

        instances = db.scalars(select(TimetableInstance).where(
            TimetableInstance.generation_id == gen.id)).all()
        print(f"instances: {len(instances)}")

        all_ok = True
        for inst in instances:
            slots = db.scalars(select(TimetableSlot).where(
                TimetableSlot.instance_id == inst.id)).all()
            issues = audit(slots, db)
            total = sum(len(v) for v in issues.values())
            print(f"\ninstance {inst.id} (#{inst.instance_number}, "
                  f"status={inst.status.value}): {len(slots)} slots, {total} issue(s)")
            for kind, entries in issues.items():
                if entries:
                    all_ok = False
                    print(f"  [{kind}] {len(entries)}")
                    for e in entries[:5]:
                        print(f"    - {e}")
                    if len(entries) > 5:
                        print(f"    ... +{len(entries) - 5} more")
        print("\nVERDICT:", "CLEAN — no conflicts found" if all_ok else "ISSUES FOUND")
        return 0 if all_ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
