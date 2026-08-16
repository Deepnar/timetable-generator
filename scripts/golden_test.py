#!/usr/bin/env python3
"""Golden fidelity test (Phase 5, A8): regenerate every division and score it.

Solves every profile fresh (no published-conflict reservations) and scores
the result with ``app/engine/fidelity.py`` against the published grids and
the college's own rules. Exits non-zero when a metric regresses, so a solver
change that quietly degrades the output fails here before it ships.

Usage:
    uv run python -m scripts.golden_test [--codes COMP] [--slack]

``--slack`` downgrades the assertions to a report (no failure) — useful when
the data itself changed (a re-seed with different codes) rather than the
engine.

Metrics (audit A8): unplaced sessions == 0; weekly hours per (subject,
division) within ±1 of the grid (PROJECT excluded — the college has not
named mentors); break-slot sessions == 0; Saturday sessions == 0; lecture
room stability >= 0.95; teachers per (subject, division) <= 2.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from app.database import SessionLocal
from app.engine.profile_resolver import ProfileResolver
from app.engine.solvers.greedy_solver import GreedySolver
from app.engine.fidelity import (
    hours_deltas, break_slot_violations, saturday_violations, room_stability,
    teachers_per_subject_group, grid_gap_subjects,
)
from app.models.profiles import TimetableProfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codes", default="COMP",
                        help="comma-separated department codes to score")
    parser.add_argument("--slack", action="store_true",
                        help="report regressions without failing")
    args = parser.parse_args()
    codes = {c.strip().upper() for c in args.codes.split(",") if c.strip()}

    db = SessionLocal()
    results: list[dict] = []
    t0 = time.time()
    for prof in db.query(TimetableProfile).order_by(TimetableProfile.id).all():
        dept = prof.name.split("—")[-1].strip().split("-")[0]
        if dept not in codes:
            continue
        resolved = ProfileResolver(db).resolve(prof.id)
        solver = GreedySolver(db=db, profile=resolved, instance_id=-prof.id)
        slots = solver.solve()
        results.append({
            "profile": prof.id,
            "name": prof.name,
            "unplaced": solver.unplaced_count,
            "placed": len(slots),
            "break_violations": break_slot_violations(
                db, -prof.id, solver._break_slots(), slots=slots),
            "saturday_violations": saturday_violations(
                db, -prof.id,
                str(resolved.params.get("saturday_policy", "NONE")),
                slots=slots),
            "room_stability": room_stability(db, -prof.id, slots=slots),
        })
    solve_time = time.time() - t0

    timetables = [t for t in json.load(
        open("info/import/timetables.json"))["timetables"]
        if t["group_name"].split("-")[0] in codes]
    subjects = json.load(open("info/import/subjects.json"))["subjects"]
    code_to_name = {
        (s["department_code"], s["semester"], s["code"]): s["name"]
        for s in subjects
    }
    bad, total = hours_deltas(db, timetables, code_to_name)
    # Grid-side gaps (the college named no teacher for the subject — PROJECT,
    # online electives) are the registrar's to fix, not solver regressions.
    gaps = grid_gap_subjects(timetables)
    bad_non_project = [b for b in bad
                       if (b[0], b[1]) not in gaps and b[1] != "PROJECT"]

    print(f"=== golden fidelity: {', '.join(sorted(codes))} "
          f"({len(results)} profiles, {solve_time:.2f}s) ===")
    print(f"{'profile':>8}  {'unplaced':>8}  {'break':>5}  {'sat':>3}  "
          f"{'stability':>9}")
    for r in results:
        stab = f"{r['room_stability']:.2f}" if r["room_stability"] is not None else "-"
        print(f"{r['profile']:>8}  {r['unplaced']:>8}  "
              f"{r['break_violations']:>5}  {r['saturday_violations']:>3}  "
              f"{stab:>9}  {r['name']}")
    print(f"hours outside +-1: {len(bad)}/{total} "
          f"(solver-attributable: {len(bad_non_project)}, "
          f"grid gaps: {len(bad) - len(bad_non_project)})")
    if bad_non_project:
        for b in bad_non_project:
            print("   ", b)

    failures: list[str] = []
    if any(r["unplaced"] for r in results):
        failures.append("unplaced sessions present")
    if any(r["break_violations"] for r in results):
        failures.append("sessions in break slots")
    if any(r["saturday_violations"] for r in results):
        failures.append("Saturday sessions under policy NONE")
    if bad_non_project:
        failures.append("weekly hours outside +-1 (non-PROJECT)")
    low_stability = [r for r in results
                     if r["room_stability"] is not None
                     and r["room_stability"] < 0.95]
    if low_stability:
        failures.append(
            f"room stability < 0.95 ({len(low_stability)} divisions)")

    teachers = teachers_per_subject_group(db)
    over = {k: v for k, v in teachers.items() if v > 2}
    if over:
        failures.append(f"teachers per (subject, division) > 2: {over}")

    if failures:
        print("GOLDEN FAILURES:", "; ".join(failures))
        return 1 if not args.slack else 0
    print("golden: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
