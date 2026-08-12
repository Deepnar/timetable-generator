"""Battle-test the generation engine at realistic college scale.

Runs real generations (greedy + OR-Tools) against the dataset produced by
``scripts.seed_demo.py`` and reports timing, session placement, and instance
quality per run. Uses the same ``Scheduler`` the API calls, so this exercises
the real engine path end-to-end against live Postgres.

Usage:
    uv run python -m scripts.battle_test [--all-departments] [--or-tools]

By default it runs greedy on a representative sample (2 per-semester profiles
and 2 whole-department profiles). ``--all-departments`` runs greedy on every
whole-department profile. ``--or-tools`` also runs OR-Tools on the per-semester
profiles. Results print as a table.

This is a dev/testing tool, not part of the API surface.
"""
from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import select

from app.database import SessionLocal
from app.engine.scheduler import Scheduler
from app.models.generation import (
    TimetableGeneration, TimetableInstance, TimetableSlot, AlgorithmType,
    VariationMode,
)
from app.models.profiles import TimetableProfile


def _profile(db, name_fragment: str) -> TimetableProfile:
    prof = db.scalars(select(TimetableProfile).where(
        TimetableProfile.name.like(f"%{name_fragment}%")
    )).first()
    if prof is None:
        raise SystemExit(f"no profile matching '{name_fragment}' — run the seed first")
    return prof


def _run(db, profile_id: int, algorithm: AlgorithmType, admin_id: int,
         instances: int = 1, variation: VariationMode = VariationMode.RANDOM,
         label: str = "") -> dict:
    sched = Scheduler(db)
    t0 = time.monotonic()
    generation = sched.run(
        profile_id=profile_id,
        timetable_type="CLASS",
        academic_year="2026-27",
        semester=None,
        instances_requested=instances,
        algorithm=algorithm,
        triggered_by=admin_id,
        variation=variation,
    )
    wall = time.monotonic() - t0

    instance_rows = db.scalars(select(TimetableInstance).where(
        TimetableInstance.generation_id == generation.id)).all()
    instance_ids = [i.id for i in instance_rows]
    slot_count = 0
    if instance_ids:
        from sqlalchemy import func
        slot_count = db.scalar(select(func.count()).select_from(
            TimetableSlot).where(
            TimetableSlot.instance_id.in_(instance_ids))) or 0

    return {
        "label": label or f"#{generation.id}",
        "algorithm": algorithm.value,
        "instances": len(instance_rows),
        "slots": slot_count,
        "status": generation.generation_status.value,
        "run_duration_ms": generation.run_duration_ms,
        "wall_s": round(wall, 2),
        "best_score": generation.score_best_instance,
        "error": generation.error_log,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-departments", action="store_true")
    parser.add_argument("--or-tools", action="store_true")
    parser.add_argument("--instances", type=int, default=1)
    parser.add_argument("--multi-department", action="store_true",
                        help="run 3-instance greedy on one whole-department profile "
                             "(exercises the diversity filter at scale)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        from app.models.admin import Admin
        admin = db.query(Admin).first()
        if admin is None:
            raise SystemExit("no admin — run scripts.seed_demo first")

        results = []

        # 1) greedy on 2 per-semester profiles (the TCET TE-D-style unit)
        for frag in ("Computer Engineering — TE", "Mechanical Engineering — SE"):
            prof = _profile(db, frag)
            results.append(_run(db, prof.id, AlgorithmType.GREEDY, admin.id,
                                 instances=args.instances, label=prof.name))

        # 2) greedy on whole-department profiles (the big scale)
        if args.all_departments:
            dept_profiles = db.scalars(select(TimetableProfile).where(
                TimetableProfile.scope_type == "DEPARTMENT")).all()
            for prof in dept_profiles:
                results.append(_run(db, prof.id, AlgorithmType.GREEDY, admin.id,
                                    instances=args.instances, label=prof.name))
        else:
            for frag in ("Computer Engineering — All", "Information Technology — All"):
                prof = _profile(db, frag)
                results.append(_run(db, prof.id, AlgorithmType.GREEDY, admin.id,
                                    instances=args.instances, label=prof.name))

        # 3) OR-Tools on a per-semester profile (CP-SAT scale, 5s timeout)
        if args.or_tools:
            prof = _profile(db, "Computer Engineering — TE")
            results.append(_run(db, prof.id, AlgorithmType.OR_TOOLS, admin.id,
                                instances=args.instances, label=f"{prof.name} [OR-Tools]"))

        # 4) multi-instance greedy on a whole department (diversity filter at scale)
        if args.multi_department:
            prof = _profile(db, "Computer Engineering — All")
            results.append(_run(db, prof.id, AlgorithmType.GREEDY, admin.id,
                                instances=3, label=f"{prof.name} [3 instances]"))

        print()
        header = f"{'run':<44} {'algo':<9} {'inst':>4} {'slots':>6} {'status':<10} {'dur_ms':>8} {'wall_s':>8} {'score':>6}"
        print(header)
        print("-" * len(header))
        for r in results:
            print(f"{r['label'][:44]:<44} {r['algorithm']:<9} {r['instances']:>4} "
                  f"{r['slots']:>6} {r['status']:<10} {r['run_duration_ms']:>8} "
                  f"{r['wall_s']:>8} {('%.2f' % r['best_score']) if r['best_score'] is not None else '-':>6}")
        print()
        failed = [r for r in results if r["status"] != "COMPLETED"]
        if failed:
            print("FAILED runs:")
            for r in failed:
                print(f"  {r['label']}: {r['error']}")
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
