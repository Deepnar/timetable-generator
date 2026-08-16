"""Synthetic problem generator (D4): plant a valid timetable, derive inputs.

The old ``build_synthetic_branches.py`` invented people; a solver bug was
indistinguishable from an incoherent fake roster. This generator does the
opposite:

1. Pick a shape (divisions, subjects, batches, slots, rooms, teachers).
2. **Construct a valid timetable first** — lay sessions into slots by pattern,
   respecting every invariant the solver enforces (double-booking, break
   slots, max-one-lab-per-day, home rooms, window co-location, distinct
   faculty per window batch, same-subject-same-day for lectures). This is
   easy because there is no search — just a pattern.
3. **Derive the inputs from it** — weekly hours = how many times each subject
   was placed, teacher assignments = who was placed, rooms = what was used,
   batch rows per lab window with period/block.

Any unplaced session in a solve of the derived inputs is then **provably a
solver bug**, and the planted timetable is a known optimum to score against.
The generator writes directly to a DB session (the SQLite test DB in tests;
Postgres for scripts). It is generic — no college names or constants.
"""
from __future__ import annotations

import json

from app.models.profiles import (
    TimetableProfile, ProfileResource, ProfileParameter, ResourceType,
    ScopeType, ParamType,
)
from app.models.groups import StudentGroup, GroupType
from app.models.rooms import Room, RoomType
from app.models.subjects import Subject
from app.models.faculty import Faculty
from app.models.subject_assignments import SubjectAssignment
from app.models.constraints import HardConstraint
from app.engine.constraint_registry import DEFAULT_INSTITUTIONAL_CONFIGS

_DAY_NAMES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def _slot_times(count: int) -> list[list[str]]:
    """Slot times "HH:MM" per slot, 60 minutes each starting at 08:00."""
    out = []
    for i in range(count):
        start = 8 + i
        out.append([f"{start:02d}:00", f"{start + 1:02d}:00"])
    return out


def plant_problem(
    db,
    *,
    divisions: int = 2,
    subjects_per_division: int = 3,
    lecture_hours: int = 2,
    batches: int = 2,
    slots: int = 6,
    break_slot: int = 3,
    days: int = 5,
    lab_block: int = 2,
    home_rooms: bool = True,
    admin_id: int | None = None,
    department: str = "SYN",
) -> dict:
    """Plant a valid timetable and derive the solver's inputs from it.

    Returns a dict with the created ids and the planted placements::

        {"profile": int, "groups": [ids], "planted": [(group_id, subject_id,
         faculty_id, day, slot, block_length, batch_number), ...]}

    Every placement respects the same rules the solver enforces, so the
    derived problem is guaranteed-satisfiable.
    """
    from sqlalchemy import select
    from app.models.admin import Admin

    if admin_id is None:
        admin_id = db.scalars(select(Admin.id).order_by(Admin.id)).first()
    if admin_id is None:
        raise ValueError("plant_problem needs an admin row first (create_admin)")

    prof = TimetableProfile(
        name=f"{department} cohort", scope_type=ScopeType.DIVISION,
        academic_year="2026-27", semester=4, department=department,
        created_by=admin_id,
    )
    db.add(prof)
    db.flush()
    db.add_all([
        ProfileParameter(profile_id=prof.id, param_key="slots_per_day",
                         param_value=str(slots), param_type=ParamType.INT),
        ProfileParameter(profile_id=prof.id, param_key="slot_times",
                         param_value=json.dumps(_slot_times(slots)),
                         param_type=ParamType.JSON),
        ProfileParameter(profile_id=prof.id, param_key="break_slots",
                         param_value=json.dumps([break_slot]),
                         param_type=ParamType.JSON),
        ProfileParameter(profile_id=prof.id, param_key="working_days",
                         param_value=json.dumps(_DAY_NAMES[:days]),
                         param_type=ParamType.JSON),
        ProfileParameter(profile_id=prof.id, param_key="saturday_policy",
                         param_value="NONE", param_type=ParamType.STRING),
        ProfileParameter(profile_id=prof.id, param_key="term_start",
                         param_value="2026-07-06", param_type=ParamType.STRING),
    ])
    for rule_type, config in DEFAULT_INSTITUTIONAL_CONFIGS.items():
        db.add(HardConstraint(profile_id=None, constraint_type=rule_type,
                              config_json=dict(config)))

    groups: list[StudentGroup] = []
    for i in range(divisions):
        g = StudentGroup(name=f"{department}-{chr(65 + i)}",
                         group_type=GroupType.DIVISION, department=department,
                         year=2, semester=4, strength=60)
        db.add(g)
        db.flush()
        groups.append(g)
        db.add(ProfileResource(profile_id=prof.id,
                               resource_type=ResourceType.STUDENT_GROUP,
                               resource_id=g.id))

    lab_rooms: list[Room] = []
    home_rooms_list: list[Room] = []
    for i in range(divisions):
        # One classroom per division. With home_rooms=True it becomes the
        # division's venue (the solver hard-restricts lectures to it); with
        # False it is just pool space and lectures may scatter.
        home = Room(name=f"{department}-CR-{i + 1}", room_code=f"CR{i + 1}",
                    room_type=RoomType.CLASSROOM, capacity=80, building="A")
        db.add(home)
        db.flush()
        home_rooms_list.append(home)
        if home_rooms:
            groups[i].home_room_id = home.id
        db.add(ProfileResource(profile_id=prof.id,
                               resource_type=ResourceType.ROOM,
                               resource_id=home.id))
    for i in range(max(2, batches)):
        lab = Room(name=f"{department}-LAB-{i + 1}", room_code=f"LAB{i + 1}",
                   room_type=RoomType.LAB, capacity=40, building="B")
        db.add(lab)
        db.flush()
        lab_rooms.append(lab)
        db.add(ProfileResource(profile_id=prof.id,
                               resource_type=ResourceType.ROOM,
                               resource_id=lab.id))

    # Faculty: one per (division, subject); a lab window gets the subject's
    # teacher for batch 1 plus dedicated teachers for the remaining batches,
    # so every window is co-locatable (distinct faculty per batch).
    subjects: dict[int, list[Subject]] = {}
    faculty_by_subject: dict[tuple[int, int], int] = {}
    for gi, g in enumerate(groups):
        subs: list[Subject] = []
        for si in range(subjects_per_division):
            is_lab = si == subjects_per_division - 1
            s = Subject(
                name=f"SUB{si + 1}" + (" Lab" if is_lab else ""),
                subject_code=f"{g.name}-S{si + 1}",
                department=department, semester=4,
                hours_per_week=lecture_hours,
                requires_lab=is_lab,
                requirements_json=(
                    {"session_type": "LAB", "room_types": ["LAB"]} if is_lab
                    else {"session_type": "LECTURE",
                          "room_types": ["CLASSROOM"]}),
            )
            db.add(s)
            db.flush()
            subs.append(s)
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.SUBJECT,
                                   resource_id=s.id))
            fac = Faculty(name=f"T {department}-{chr(65 + gi)}-{si + 1}",
                          email=f"t{gi}{si}@syn.in", department=department)
            db.add(fac)
            db.flush()
            faculty_by_subject[(g.id, s.id)] = fac.id
            db.add(ProfileResource(profile_id=prof.id,
                                   resource_type=ResourceType.FACULTY,
                                   resource_id=fac.id))
        subjects[g.id] = subs

    # ── plant the timetable ─────────────────────────────────
    planted: list[tuple] = []
    occupied_group: dict[int, list[tuple[int, int, int]]] = {}
    occupied_faculty: dict[int, list[tuple[int, int, int]]] = {}
    occupied_room: dict[int, list[tuple[int, int, int]]] = {}
    lab_days: dict[int, set[int]] = {}
    subject_days: dict[tuple[int, int], set[int]] = {}

    def busy(occ, key, day, slot, length=1) -> bool:
        return any(
            d == day and not (slot + length - 1 < s or s + ln - 1 < slot)
            for (d, s, ln) in occ.get(key, [])
        )

    def occupy(occ, key, day, slot, length=1) -> None:
        occ.setdefault(key, []).append((day, slot, length))

    def free_slots(group_id, faculty_id, room_id, length=1) -> list[tuple[int, int]]:
        out = []
        for day in range(days):
            for sn in range(1, slots + 1):
                if sn == break_slot or sn + length - 1 == break_slot:
                    continue
                if sn + length - 1 > slots:
                    continue
                if busy(occupied_group, group_id, day, sn, length):
                    continue
                if busy(occupied_faculty, faculty_id, day, sn, length):
                    continue
                if busy(occupied_room, room_id, day, sn, length):
                    continue
                out.append((day, sn))
        return out

    # Lectures: one per subject per day at most (SAME_SUBJECT_SAME_DAY),
    # spaced across the week, in the division's venue.
    for gi, g in enumerate(groups):
        for s in subjects[g.id]:
            if s.requires_lab:
                continue
            fid = faculty_by_subject[(g.id, s.id)]
            room = home_rooms_list[gi]
            placed_this = 0
            for day in range(days):
                if placed_this >= lecture_hours:
                    break
                if day in subject_days.get((g.id, s.id), set()):
                    continue
                for sn in range(1, slots + 1):
                    if sn == break_slot:
                        continue
                    if busy(occupied_group, g.id, day, sn):
                        continue
                    if busy(occupied_faculty, fid, day, sn):
                        continue
                    if busy(occupied_room, room.id, day, sn):
                        continue
                    occupy(occupied_group, g.id, day, sn)
                    occupy(occupied_faculty, fid, day, sn)
                    occupy(occupied_room, room.id, day, sn)
                    subject_days.setdefault((g.id, s.id), set()).add(day)
                    planted.append((g.id, s.id, fid, day, sn, 1, None))
                    placed_this += 1
                    break
            if placed_this < lecture_hours:
                raise RuntimeError(
                    f"plant failed: only {placed_this}/{lecture_hours} "
                    f"lectures of {s.name} placed (shape too dense)")

    # Lab windows: one per lab subject per week; every batch co-located at
    # (day, slot) spanning lab_block slots in distinct rooms; at most one lab
    # window per group per day (MAX_ONE_LAB_PER_DAY). All batches validate
    # before anything is committed, so a failed attempt leaves no residue.
    for gi, g in enumerate(groups):
        for s in subjects[g.id]:
            if not s.requires_lab:
                continue
            base_fid = faculty_by_subject[(g.id, s.id)]
            extra_fids: list[int] = []
            for _ in range(batches - 1):
                fac = Faculty(name=f"L {department}-{g.name}-{s.name}-{len(extra_fids)}",
                              email=f"l{gi}{len(extra_fids)}@syn.in",
                              department=department)
                db.add(fac)
                db.flush()
                extra_fids.append(fac.id)
                db.add(ProfileResource(profile_id=prof.id,
                                       resource_type=ResourceType.FACULTY,
                                       resource_id=fac.id))
            batch_fids = [base_fid] + extra_fids
            placed = False
            for day in range(days):
                if day in lab_days.get(g.id, set()):
                    continue
                for sn in range(1, slots + 1):
                    if sn == break_slot or sn + lab_block - 1 == break_slot:
                        continue
                    if sn + lab_block - 1 > slots:
                        continue
                    if busy(occupied_group, g.id, day, sn, lab_block):
                        continue
                    room_for: dict[int, Room] = {}
                    used_rooms: set[int] = set()
                    ok = True
                    for b in range(batches):
                        if busy(occupied_faculty, batch_fids[b], day, sn,
                                lab_block):
                            ok = False
                            break
                        room = next(
                            (lab for lab in lab_rooms
                             if lab.id not in used_rooms
                             and not busy(occupied_room, lab.id, day, sn,
                                          lab_block)),
                            None)
                        if room is None:
                            ok = False
                            break
                        room_for[b] = room
                        used_rooms.add(room.id)
                    if not ok:
                        continue
                    occupy(occupied_group, g.id, day, sn, lab_block)
                    for b, room in room_for.items():
                        occupy(occupied_faculty, batch_fids[b], day, sn,
                               lab_block)
                        occupy(occupied_room, room.id, day, sn, lab_block)
                        planted.append((g.id, s.id, batch_fids[b], day, sn,
                                        lab_block, b + 1))
                    lab_days.setdefault(g.id, set()).add(day)
                    placed = True
                    break
                if placed:
                    break
            if not placed:
                raise RuntimeError(
                    f"plant failed: lab window of {s.name} could not be "
                    f"placed (shape too dense)")

    # ── derive the assignment rows from what was placed ──────
    for g in groups:
        for si, s in enumerate(subjects[g.id]):
            if not s.requires_lab:
                continue
            for b in range(1, batches + 1):
                row_fid = next(
                    (f for (gid, sid, f, _d, _sn, _bl, bb) in planted
                     if gid == g.id and sid == s.id and bb == b), None)
                if row_fid is None:
                    continue
                db.add(SubjectAssignment(
                    subject_id=s.id, faculty_id=row_fid, group_id=g.id,
                    weekly_hours=1, load_share=1.0,
                    batch_number=b, period_number=si + 1,
                    block_length=lab_block))
    for g in groups:
        for s in subjects[g.id]:
            if s.requires_lab:
                continue
            fid = faculty_by_subject[(g.id, s.id)]
            n = sum(1 for (gid, sid, f, _d, _sn, _bl, b) in planted
                    if gid == g.id and sid == s.id and b is None)
            db.add(SubjectAssignment(
                subject_id=s.id, faculty_id=fid, group_id=g.id,
                weekly_hours=n, load_share=1.0))
    db.flush()
    return {
        "profile": prof.id,
        "groups": [g.id for g in groups],
        "planted": planted,
    }
