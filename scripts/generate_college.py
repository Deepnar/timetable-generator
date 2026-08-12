"""Generate and publish a timetable for EVERY class in the college.

This is the end-of-project "proper seed" (founder's final goal, OPEN 13): it
takes the seeded dataset (``scripts.seed_demo.py``) and produces a live,
published timetable for each CLASS — one per division, 192 in total
(12 departments x 4 years FE/SE/TE/BE x 4 divisions A-D). No years are
merged: each instance is exactly one class's clean timetable.

Usage:
    uv run python -m scripts.seed_demo --wipe   # fresh dataset (server NOT needed)
    uv run python -m scripts.generate_college [--instances 1] [--dry-run] [--only MECH]

For each DIVISION-scoped (per-class) profile it runs greedy with ``--instances``
variations (default 1, best-wins via ``variation="best"``), picks the
highest-scoring instance, and publishes it. Publishing follows the same rules
as the API: previously published instances of that generation are archived,
and publish notifications (in-app + email, DD-027) fire best-effort.

This is a dev tool, not part of the API surface.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from sqlalchemy import select, func

from app.database import SessionLocal
from app.engine.scheduler import Scheduler
from app.models.admin import Admin
from app.models.generation import (
    TimetableGeneration, TimetableInstance, TimetableSlot,
    InstanceStatus, AlgorithmType, VariationMode,
)
from app.models.profiles import TimetableProfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", type=int, default=1,
                        help="instances per class (best-wins variation)")
    parser.add_argument("--dry-run", action="store_true",
                        help="generate but do not publish")
    parser.add_argument("--only", type=str, default=None,
                        help="run one department by name fragment (e.g. MECH)")
    parser.add_argument("--clear-locks", action="store_true",
                        help="delete stale Redis generation locks first (safe when "
                             "no other generation is running — a killed worker "
                             "leaves its lock until the 600s TTL expires)")
    args = parser.parse_args()

    if args.clear_locks:
        from app.services import redis_client
        client = redis_client._get_client()
        if client is not None:
            for k in list(client.scan_iter(match="timetable:lock:*")):
                client.delete(k)
                print(f"cleared stale lock {k[:60]}")

    db = SessionLocal()
    try:
        admin = db.query(Admin).first()
        if admin is None:
            raise SystemExit("no admin — run scripts.seed_demo first")

        profiles = db.scalars(
            select(TimetableProfile).where(
                TimetableProfile.scope_type == "DIVISION"
            ).order_by(TimetableProfile.department, TimetableProfile.semester,
                       TimetableProfile.name)
        ).all()
        if args.only:
            profiles = [p for p in profiles if args.only.lower() in p.department.lower()]
        if not profiles:
            raise SystemExit(f"no DIVISION profiles found (only={args.only})")

        print(f"Generating a timetable for every class "
              f"({len(profiles)} classes, {args.instances} instance each)…")
        print()

        results = []
        for prof in profiles:
            t0 = time.monotonic()
            sched = Scheduler(db)
            generation = sched.run(
                profile_id=prof.id,
                timetable_type="CLASS",
                academic_year=prof.academic_year or "2026-27",
                semester=None,
                instances_requested=args.instances,
                algorithm=AlgorithmType.GREEDY,
                triggered_by=admin.id,
                variation=VariationMode.BEST,
            )
            wall = time.monotonic() - t0

            instances = db.scalars(select(TimetableInstance).where(
                TimetableInstance.generation_id == generation.id)).all()
            slot_count = 0
            if instances:
                slot_count = db.scalar(select(func.count()).select_from(
                    TimetableSlot).where(
                    TimetableSlot.instance_id.in_([i.id for i in instances]))) or 0

            row = {
                "name": prof.name,
                "department": prof.department,
                "generation": generation.id,
                "instances": len(instances),
                "slots": slot_count,
                "status": generation.generation_status.value,
                "wall_s": round(wall, 2),
                "best_score": generation.score_best_instance,
                "published": False,
                "error": generation.error_log,
            }

            if generation.generation_status.value == "COMPLETED" and instances and not args.dry_run:
                best = max(instances, key=lambda i: i.soft_score if i.soft_score is not None else -1)
                if best.status in (InstanceStatus.DRAFT.value, InstanceStatus.SELECTED.value):
                    # archive previously published of the same generation
                    for old in db.scalars(select(TimetableInstance).where(
                            TimetableInstance.generation_id == generation.id,
                            TimetableInstance.status == InstanceStatus.PUBLISHED)).all():
                        old.status = InstanceStatus.ARCHIVED
                    best.status = InstanceStatus.PUBLISHED
                    best.published_at = datetime.utcnow()
                    db.commit()
                    row["published"] = True
                    row["published_instance"] = best.id
                    # Fire the notification dispatch (in-app + email best-effort).
                    try:
                        from app.services import notification_service
                        notification_service.dispatch_publish(best.id)
                    except Exception:
                        pass

            results.append(row)
            print(f"  {row['name'][:44]:<44} gen {row['generation']:>3} "
                  f"inst {row['instances']:>2} slots {row['slots']:>3} "
                  f"{row['status']:<10} {row['wall_s']:>5.2f}s "
                  f"{('%.3f' % row['best_score']) if row['best_score'] is not None else '-':>8} "
                  f"{'PUBLISHED' if row['published'] else ''}")

        print()
        ok = [r for r in results if r["status"] == "COMPLETED"]
        published = [r for r in results if r["published"]]
        print(f"Completed {len(ok)}/{len(results)} classes; "
              f"{len(published)} published.")
        failed = [r for r in results if r["status"] != "COMPLETED"]
        if failed:
            print("FAILED:")
            for r in failed:
                print(f"  {r['name']}: {r['error']}")
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
