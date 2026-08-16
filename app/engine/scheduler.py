"""Orchestrates the full timetable generation run.

Flow:
1. Resolve the input contract — a single profile or a merged combination —
   into an effective profile (see ``app/engine/profile_resolver.py``).
2. Create a ``TimetableGeneration`` record (status=PENDING).
3. Load cross-timetable conflicts from any PUBLISHED instance.
4. Run the solver N times for N candidate instances.
5. Save all slots and mark the run COMPLETED.

The run is split into two entry points so it can be executed either inline
(``run()`` — the synchronous HTTP path) or by a background worker:

* ``create_generation()`` — validate the input contract and persist the
  PENDING run row so the API can return a ``run_id`` immediately. It also
  computes the pre-solve feasibility report (A4): a generation whose demand
  cannot fit the real capacity fails here, loudly, instead of completing with
  a warning.
* ``solve_generation()`` — load a run by id, solve it, and flip the row to
  COMPLETED (or FAILED with ``error_log``), stamping ``run_duration_ms``.
"""
import time
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.generation import (
    TimetableGeneration,
    TimetableInstance,
    TimetableSlot,
    GenerationStatus,
    InstanceStatus,
    AlgorithmType,
    VariationMode,
)
from app.models.subject_assignments import SubjectAssignment
from app.models.rooms import Room, RoomType
from app.models.groups import StudentGroup
from app.models.faculty import Faculty
from app.models.subjects import Subject
from app.services.settings_service import get_settings
from app.services import redis_client
from app.models.profiles import ResourceType
from app.engine.profile_resolver import ProfileResolver
from app.engine.solvers.greedy_solver import GreedySolver
from app.engine.constraint_checker import ConstraintChecker, SlotCandidate
from app.engine.scorer import score_instance, ScoringContext


class GenerationLockError(RuntimeError):
    """Raised when a generation cannot run because another run is already
    solving the same resources. The run row is marked FAILED before raising."""


class FeasibilityError(RuntimeError):
    """Raised when a generation's demand cannot fit the real capacity.

    The run row is marked FAILED with the feasibility report as ``error_log``
    before raising, so both the sync path (409 to the client) and the async
    worker see an honest failure instead of a COMPLETED run with a warning."""

    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report


class Scheduler:
    """Coordinator between the API and the solver."""

    # Diversity filter: how many seeds to try per instance, and the minimum
    # number of differing slot placements for two instances to count as distinct.
    _DIVERSITY_ATTEMPTS = 6
    _DIVERSITY_MIN_DISTANCE = 1

    def __init__(self, db: Session):
        self.db = db

    def run(
        self,
        profile_id: int | None,
        timetable_type: str,
        academic_year: str,
        semester: int | None,
        instances_requested: int,
        algorithm: AlgorithmType,
        triggered_by: int,
        combination_id: int | None = None,
        variation: VariationMode = VariationMode.RANDOM,
    ) -> TimetableGeneration:
        """Synchronous entry point: create the run and solve it in one call."""
        generation = self.create_generation(
            profile_id=profile_id,
            timetable_type=timetable_type,
            academic_year=academic_year,
            semester=semester,
            instances_requested=instances_requested,
            algorithm=algorithm,
            triggered_by=triggered_by,
            combination_id=combination_id,
            variation=variation,
        )
        return self.solve_generation(generation.id)

    def create_generation(
        self,
        profile_id: int | None,
        timetable_type: str,
        academic_year: str,
        semester: int | None,
        instances_requested: int,
        algorithm: AlgorithmType,
        triggered_by: int,
        combination_id: int | None = None,
        variation: VariationMode = VariationMode.RANDOM,
    ) -> TimetableGeneration:
        """Validate the input contract and persist the PENDING run row.

        Raising on a missing/inactive profile/combination up front means the
        API can reject a bad request immediately (404) instead of waiting for
        the worker to discover it. The solver input is resolved once here and
        again in :meth:`solve_generation`, which re-resolves from the run row
        (``profile_id`` / ``combination_id``) so a worker that only receives a
        ``run_id`` needs nothing else.
        """
        # Resolve the input contract once: a single profile, or a combination
        # merged into an effective profile (see app/engine/profile_resolver.py).
        # The generation row keeps profile_id/combination_id as the user asked
        # while the solver consumes the merged view.
        resolved = ProfileResolver(self.db).resolve(profile_id, combination_id)

        generation = TimetableGeneration(
            profile_id=resolved.profile_id,
            combination_id=combination_id,
            academic_year=academic_year,
            semester=semester,
            timetable_type=timetable_type,
            instances_requested=instances_requested,
            algorithm_used=algorithm,
            variation=variation,
            triggered_by=triggered_by,
            generation_status=GenerationStatus.PENDING,
        )
        self.db.add(generation)
        self.db.flush()

        # Pre-solve feasibility report (A4): a run whose demand cannot fit the
        # real capacity must fail HERE, loudly, not complete with a warning
        # string. The report is stored on the row either way so the UI can
        # show the balance even when the run proceeds.
        report = self._feasibility_report(resolved)
        generation.feasibility_report = report
        if not report["feasible"]:
            generation.generation_status = GenerationStatus.FAILED
            generation.error_log = report["summary"]
            generation.completed_at = datetime.utcnow()
            self.db.commit()
            report = {**report, "run_id": generation.id}
            raise FeasibilityError(report["summary"], report)
        self.db.flush()
        return generation

    def solve_generation(self, generation_id: int) -> TimetableGeneration:
        """Solve a run row and flip it to COMPLETED (or FAILED).

        Re-resolves the profile from the run row so a worker holding only the
        ``run_id`` can run the full pipeline. On any exception the row is
        marked ``FAILED`` with ``error_log`` and the exception is re-raised
        (the synchronous router turns it into a 500; the Celery task swallows
        it because the row already records the failure).
        """
        start = time.time()
        generation = self.db.get(TimetableGeneration, generation_id)
        if generation is None:
            raise ValueError(f"Generation run {generation_id} not found")

        # Serialise generations over the same resource set: two concurrent
        # solves would otherwise each compute their own (empty) published
        # reservations and could both place the same faculty/room/group in the
        # same slot. A Redis-disabled/unreachable setup degrades to running
        # unlocked; a busy lock means another run already owns these resources,
        # so this run is marked FAILED instead of racing it.
        lock = self._acquire_resource_lock(generation)
        if lock is False:
            generation.generation_status = GenerationStatus.FAILED
            generation.error_log = (
                "Another generation over the same resources is already running"
            )
            generation.completed_at = datetime.utcnow()
            generation.run_duration_ms = int((time.time() - start) * 1000)
            self.db.commit()
            raise GenerationLockError(
                f"Another generation over the same resources is already running "
                f"(run {generation_id} marked FAILED)"
            )

        try:
            return self._solve(generation, start)
        except Exception as exc:
            self.db.rollback()
            failed = self.db.get(TimetableGeneration, generation_id)
            if failed is not None:
                failed.generation_status = GenerationStatus.FAILED
                failed.error_log = str(exc)
                failed.completed_at = datetime.utcnow()
                failed.run_duration_ms = int((time.time() - start) * 1000)
                self.db.commit()
            raise
        finally:
            redis_client.release_lock(lock)

    def _acquire_resource_lock(self, generation):
        """Lock the union of the run's resource ids so a concurrent generation
        cannot reuse the same faculty/room/group slots.

        Returns the :class:`redis_client.Lock` when acquired, ``False`` when it
        is already held, or ``None`` (run unlocked) when Redis is unavailable or
        the input contract cannot be resolved (``_solve`` reports that failure
        itself).
        """
        try:
            resolved = ProfileResolver(self.db).resolve(
                generation.profile_id, generation.combination_id
            )
        except ValueError:
            return None
        ids: set[int] = set()
        for rt in ResourceType:
            ids.update(resolved.resource_ids(rt))
        key = "timetable:lock:generate:" + (
            ",".join(str(i) for i in sorted(ids)) if ids else "empty"
        )
        return redis_client.acquire_lock(key)

    def _solve(
        self, generation: TimetableGeneration, start: float
    ) -> TimetableGeneration:
        # Re-resolve the input contract from the run row so a worker holding
        # only the run_id can run the full pipeline (profile_id for a single
        # profile, combination_id for a merged combination).
        resolved = ProfileResolver(self.db).resolve(
            generation.profile_id, generation.combination_id
        )

        generation.generation_status = GenerationStatus.RUNNING
        self.db.flush()

        # Pre-load slots from every PUBLISHED instance, so the solver
        # can never double-book an already-live timetable. For an exam
        # generation, the examing groups suspend their own classes, so
        # their published CLASS reservations are exempted (their slots are
        # reusable for exams) while every other group's rooms/faculty stay
        # protected — that is how one branch exams while the rest teaches.
        reserved_conflicts = self._load_published_conflicts(
            exempt_groups=(
                resolved.resource_ids(ResourceType.STUDENT_GROUP)
                if resolved.params.get("session_type") == "EXAM" else None
            )
        )

        # Soft-constraint scoring (opt-in per college). When enabled, each
        # instance is scored so the admin can rank the candidates.
        settings = get_settings(self.db)
        soft_rules = (
            resolved.soft_constraints
            if settings.enable_soft_constraint_scoring
            else []
        )
        scoring_ctx = ScoringContext(self.db)

        instances_created = 0
        best_score: float | None = None
        accepted_signatures: list[frozenset] = []
        final_unplaced = 0
        variation = generation.variation
        # A profile diversity_threshold parameter overrides the module default
        # (how many placements must differ for two instances to count as
        # distinct). Stored as a string; cast defensively.
        try:
            diversity_min = int(resolved.params.get("diversity_threshold",
                                                    self._DIVERSITY_MIN_DISTANCE))
        except (TypeError, ValueError):
            diversity_min = self._DIVERSITY_MIN_DISTANCE
        for i in range(generation.instances_requested):
            instance = TimetableInstance(
                generation_id=generation.id,
                instance_number=i + 1,
                status=InstanceStatus.DRAFT,
            )
            self.db.add(instance)
            self.db.flush()

            # Diversity: solvers are deterministic, so re-running produces the
            # same timetable. Seed each attempt differently and keep the first
            # one that differs from every already-accepted instance (falling
            # back to the last attempt if the problem is too small to vary).
            # The instance strategy ("variation") shapes *how* the seeded
            # attempts search: greedy re-orders by criterion and OR-Tools adds
            # a secondary gap objective (minimize-teacher/student-gaps), while
            # "best" keeps the highest-scoring distinct attempt so instance #1
            # can be the best timetable instead of the plain deterministic
            # baseline.
            attempts: list[tuple[list, frozenset, float | None]] = []
            for attempt in range(self._DIVERSITY_ATTEMPTS):
                if variation == VariationMode.BEST:
                    # "best" also seeds instance #1 so a genuine optimum can be
                    # found (the baseline is just one point in the space).
                    seed = i * 100 + attempt
                else:
                    # Instance #1 is the deterministic baseline (no seed);
                    # later instances are seeded to diverge from it.
                    seed = None if i == 0 else i * 100 + attempt
                solver = self._make_solver(
                    generation.algorithm_used, resolved, instance.id,
                    seed=seed, variation=variation,
                )
                solver.reserved_conflicts = reserved_conflicts
                candidate = solver.solve()
                candidate_sig = self._signature(candidate)
                score = (
                    score_instance(candidate, soft_rules, scoring_ctx)
                    if soft_rules else None
                )
                attempts.append((candidate, candidate_sig, score, solver.unplaced_count))
                is_distinct = all(
                    self._hamming(candidate_sig, prev)
                    >= diversity_min
                    for prev in accepted_signatures
                )
                # Quality is the default (A6): when soft rules are active every
                # attempt is scored and the best distinct one is kept below, so
                # the default path optimises instead of taking the first
                # different timetable. With no soft rules there is nothing to
                # score and the first distinct attempt still wins (diversity
                # semantics unchanged).
                if not soft_rules and variation != VariationMode.BEST and is_distinct:
                    break

            if variation == VariationMode.BEST or soft_rules:
                distinct = [
                    (c, sig, sc, u) for c, sig, sc, u in attempts
                    if all(
                        self._hamming(sig, prev) >= diversity_min
                        for prev in accepted_signatures
                    )
                ]
                pool = distinct or attempts
                if soft_rules:
                    slots, signature, score, final_unplaced = max(
                        pool, key=lambda t: t[2]
                    )
                else:
                    slots, signature, score, final_unplaced = pool[0]
            else:
                slots, signature, score, final_unplaced = attempts[-1]

            accepted_signatures.append(signature)
            for slot in slots:
                self.db.add(slot)

            # Honest hard-violation count: re-validate the committed slots with
            # the full checker (structural + registry + published conflicts).
            instance.hard_violations = self._count_instance_violations(
                slots, reserved_conflicts, resolved.hard_constraints,
                break_slots=resolved.params.get("break_slots"),
            )
            if score is not None:
                instance.soft_score = score
                best_score = score if best_score is None else max(best_score, score)

            instances_created += 1

        generation.generation_status = GenerationStatus.COMPLETED
        generation.instances_produced = instances_created
        generation.score_best_instance = best_score
        generation.completed_at = datetime.utcnow()
        generation.run_duration_ms = int((time.time() - start) * 1000)
        if final_unplaced:
            generation.placement_warning = (
                f"{final_unplaced} session(s) could not be placed "
                f"in the final instance"
            )
        self.db.commit()

        return generation

    def _feasibility_report(self, resolved) -> dict:
        """Pre-solve demand-vs-capacity report (A4).

        Compares what the solver will be asked to place against the real
        capacity of the profile's resources:

        - **per_group** — demanded sessions vs weekly slots (working_days ×
          teachable slots). Hard: exceeding this cannot be fixed by solving.
        - **per_room_type** — demanded sessions per room type vs available
          room-slots of that type. Hard: a session that needs a lab and no
          lab is free cannot be placed.
        - **per_faculty** — demanded hours per teacher vs their weekly cap.
          Informational only: the imported caps are invented placeholders
          (D6), so an over-cap teacher is reported, not a hard failure.

        The report is stored on the generation row; when a hard dimension is
        over capacity the run is marked FAILED before any solving happens.
        """
        profile_group_ids = resolved.resource_ids(ResourceType.STUDENT_GROUP)
        profile_subject_ids = resolved.resource_ids(ResourceType.SUBJECT)

        # Weekly slot capacity for the profile's groups.
        slots_per_day = 0
        try:
            slots_per_day = int(resolved.params.get("slots_per_day", 0) or 0)
        except (TypeError, ValueError):
            slots_per_day = 0
        break_slots = resolved.params.get("break_slots") or []
        if not isinstance(break_slots, list):
            break_slots = []
        try:
            teachable_per_day = max(slots_per_day - len(break_slots), 0)
        except TypeError:
            teachable_per_day = 0
        working_days = resolved.params.get("working_days") or []
        if not isinstance(working_days, list):
            working_days = []
        weekly_slots = len(working_days) * teachable_per_day

        # Demand: non-batched rows expand into weekly_hours sessions; batched
        # rows group into one window per (group, period) occupying
        # block_length slots.
        assignments = self.db.scalars(
            select(SubjectAssignment).where(
                SubjectAssignment.subject_id.in_(profile_subject_ids)
                if profile_subject_ids else True,
                SubjectAssignment.group_id.in_(profile_group_ids)
                if profile_group_ids else True,
            )
        ).all()
        group_demand: dict[int, int] = {}
        group_blocks: dict[tuple, int] = {}
        faculty_demand: dict[int, int] = {}
        session_rooms: dict[str, int] = {"LAB": 0, "CLASSROOM": 0}
        for a in assignments:
            if a.faculty_id is not None:
                faculty_demand[a.faculty_id] = (
                    faculty_demand.get(a.faculty_id, 0) + (a.weekly_hours or 1))
            if a.batch_number is not None:
                block = int(a.block_length or 1)
                group_blocks[(a.group_id, a.period_number or 1)] = max(
                    group_blocks.get((a.group_id, a.period_number or 1), 0), block)
            else:
                group_demand[a.group_id] = (
                    group_demand.get(a.group_id, 0) + (a.weekly_hours or 1))
                subject = self.db.get(Subject, a.subject_id) if a.subject_id else None
                if subject is not None:
                    stype = (subject.requirements_json or {}).get(
                        "session_type", "LECTURE")
                    key = "LAB" if stype == "LAB" else "CLASSROOM"
                    session_rooms[key] = session_rooms.get(key, 0) + (a.weekly_hours or 1)
        for (gid, _period), block in group_blocks.items():
            group_demand[gid] = group_demand.get(gid, 0) + block
            session_rooms["LAB"] = session_rooms.get("LAB", 0) + block

        per_group: list[dict] = []
        for gid in profile_group_ids:
            group = self.db.get(StudentGroup, gid)
            demand = group_demand.get(gid, 0)
            per_group.append({
                "group_id": gid,
                "name": group.name if group else str(gid),
                "demand_sessions": demand,
                "capacity_sessions": weekly_slots,
                "ok": demand <= weekly_slots,
            })

        # Room-slot capacity per type: rooms × weekly slots.
        rooms = self.db.scalars(select(Room)).all()
        room_capacity: dict[str, int] = {}
        for r in rooms:
            t = r.room_type.value if hasattr(r.room_type, "value") else str(r.room_type)
            room_capacity[t] = room_capacity.get(t, 0) + weekly_slots
        per_room_type: list[dict] = []
        for t in ("LAB", "CLASSROOM"):
            demand = session_rooms.get(t, 0)
            cap = room_capacity.get(t, 0)
            per_room_type.append({
                "room_type": t,
                "demand_sessions": demand,
                "capacity_sessions": cap,
                "ok": demand <= cap,
            })

        per_faculty: list[dict] = []
        for fid, demand in sorted(faculty_demand.items(), key=lambda kv: -kv[1]):
            fac = self.db.get(Faculty, fid)
            per_faculty.append({
                "faculty_id": fid,
                "name": fac.name if fac else str(fid),
                "demand_hours": demand,
                "max_hours_per_week": fac.max_hours_per_week if fac else None,
                "ok": demand <= (fac.max_hours_per_week if fac else demand),
            })

        hard_bad = [g for g in per_group if not g["ok"]] + \
                   [r for r in per_room_type if not r["ok"]]
        feasible = not hard_bad
        if hard_bad:
            parts = []
            for g in per_group:
                if not g["ok"]:
                    parts.append(
                        f"{g['name']} (demand {g['demand_sessions']} > "
                        f"capacity {g['capacity_sessions']})")
            for r in per_room_type:
                if not r["ok"]:
                    parts.append(
                        f"{r['room_type']} rooms (demand {r['demand_sessions']} "
                        f"> capacity {r['capacity_sessions']})")
            summary = (
                f"Pre-solve feasibility check FAILED: demand exceeds real "
                f"capacity — {', '.join(parts)}"
            )
        else:
            summary = (
                f"Pre-solve feasibility OK: {len(per_group)} group(s), "
                f"{len(per_room_type)} room type(s) within capacity"
            )
        return {
            "feasible": feasible,
            "summary": summary,
            "weekly_slots": weekly_slots,
            "per_group": per_group,
            "per_room_type": per_room_type,
            "per_faculty": per_faculty,
        }

    def _make_solver(
        self,
        algorithm: AlgorithmType,
        profile,
        instance_id: int,
        seed: int | None = None,
        variation: VariationMode = VariationMode.RANDOM,
    ):
        """Pick the solver for the requested algorithm (defaults to greedy)."""
        if algorithm == AlgorithmType.OR_TOOLS:
            # Lazy import so the heavy ortools dependency is only loaded when used.
            from app.engine.solvers.or_tools_solver import ORToolsSolver
            return ORToolsSolver(
                db=self.db, profile=profile, instance_id=instance_id,
                seed=seed, variation=variation,
            )
        return GreedySolver(
            db=self.db, profile=profile, instance_id=instance_id,
            seed=seed, variation=variation,
        )

    @staticmethod
    def _signature(slots) -> frozenset:
        """A comparable fingerprint of an instance's placements."""
        return frozenset(
            (s.student_group_id, s.day_of_week, s.slot_number, s.subject_id)
            for s in slots
        )

    @staticmethod
    def _hamming(a: frozenset, b: frozenset) -> int:
        """Number of placements that differ between two instances."""
        return len(a ^ b)

    def _count_instance_violations(self, slots, reserved_conflicts, hard_constraints,
                                   break_slots=None):
        """Re-validate an instance's committed slots with the full checker.

        The solver rejects invalid placements during solving, so committed
        slots should carry zero hard violations — but this is the honest
        count, computed by treating each *block* (contiguous same-session
        slots, e.g. a 2h lab) as a candidate against the instance's other
        blocks, the published cross-timetable reservations, and the profile's
        registry rules. Contiguous lab blocks are validated once with their
        real block_length; validating each slot individually would flag the
        second slot of a block as SAME_SUBJECT_SAME_DAY. If a bug ever lets an
        invalid slot through, `instance.hard_violations` reflects it.
        """
        if not slots:
            return 0
        ordered = sorted(
            slots, key=lambda s: (s.day_of_week or 0, s.batch_number or 0, s.slot_number)
        )
        blocks: list[list] = []
        for slot in ordered:
            if blocks:
                prev = blocks[-1][-1]
                is_continuation = (
                    prev.day_of_week == slot.day_of_week
                    and prev.slot_number + 1 == slot.slot_number
                    and prev.subject_id == slot.subject_id
                    and prev.faculty_id == slot.faculty_id
                    and prev.room_id == slot.room_id
                    and prev.student_group_id == slot.student_group_id
                )
                if is_continuation:
                    blocks[-1].append(slot)
                    continue
            blocks.append([slot])

        violations = 0
        for bi, block in enumerate(blocks):
            first = block[0]
            others = [b for bb in blocks[:bi] + blocks[bi + 1:]
                      for b in bb]
            candidate = SlotCandidate(
                instance_id=first.instance_id,
                day_of_week=first.day_of_week,
                slot_number=first.slot_number,
                start_time=first.start_time,
                end_time=block[-1].end_time,
                faculty_id=first.faculty_id,
                room_id=first.room_id,
                student_group_id=first.student_group_id,
                subject_id=first.subject_id,
                session_type=first.session_type,
                slot_date=first.slot_date,
                is_cross_department=False,
                block_length=len(block),
                batch_number=first.batch_number,
                window_key=first.window_key,
            )
            checker = ConstraintChecker(
                self.db, others, settings=get_settings(self.db),
                reserved=reserved_conflicts, hard_constraints=hard_constraints,
                break_slots={int(b) for b in break_slots} if break_slots else None,
            )
            violations += len(checker.check_all(candidate))
        return violations

    def _load_published_conflicts(
        self, exempt_groups: set[int] | None = None,
        exclude_instance_id: int | None = None
    ) -> dict[str, set[tuple]]:
        """Fetch every slot of every PUBLISHED instance.

        Returns resource-level reservations keyed by dimension::

            {
                "faculty": {(faculty_id, day, slot), ...},
                "room":    {(room_id, day, slot), ...},
                "group":   {(group_id, day, slot), ...},
            }

        Splitting per resource lets the constraint checker block a teacher,
        room, or group at a given time slot independently — a published
        booking conflicts no matter what the other two dimensions are.

        Phase 4 (A4): the dict also carries per-faculty load counts from the
        published instances — ``faculty_day_counts`` (faculty -> day ->
        slot-count) and ``faculty_week_counts`` (faculty -> slot-count) — so
        the faculty caps stay honest across runs. A teacher who already
        teaches 20h in published timetables is measured against the cap with
        that load included; without this the caps only ever saw one run's
        committed slots (a quarter of the real load for a 4-division teacher).

        ``exempt_groups``: groups whose published slots are NOT reserved. An
        exam generation passes its own groups here — a branch on exams has
        suspended its classes, so its published class slots (teacher, room,
        group) are free for the exam to reuse, while every other branch's
        active classes stay protected.

        ``exclude_instance_id``: skip one published instance entirely. Used by
        the mid-year change validation (DD-026) so a change to a published
        instance's own slot does not conflict with that same slot's published
        reservation — only *other* published timetables block it.
        """
        reserved: dict[str, set[tuple]] = {
            "faculty": set(),
            "room": set(),
            "group": set(),
            "faculty_day_counts": {},
            "faculty_week_counts": {},
        }
        exempt = set(exempt_groups or ())
        published_ids = self.db.scalars(
            select(TimetableInstance.id).where(
                TimetableInstance.status == InstanceStatus.PUBLISHED
            )
        ).all()
        if exclude_instance_id is not None:
            published_ids = [i for i in published_ids if i != exclude_instance_id]
        if not published_ids:
            return reserved

        published_slots = self.db.scalars(
            select(TimetableSlot).where(
                TimetableSlot.instance_id.in_(published_ids)
            )
        ).all()

        for slot in published_slots:
            if slot.student_group_id is not None and slot.student_group_id in exempt:
                continue
            key = (slot.day_of_week, slot.slot_number)
            if slot.faculty_id is not None:
                reserved["faculty"].add((slot.faculty_id, *key))
                week = reserved["faculty_week_counts"]
                day = reserved["faculty_day_counts"]
                week[slot.faculty_id] = week.get(slot.faculty_id, 0) + 1
                day.setdefault(slot.faculty_id, {})
                day[slot.faculty_id][slot.day_of_week] = (
                    day[slot.faculty_id].get(slot.day_of_week, 0) + 1)
            if slot.room_id is not None:
                reserved["room"].add((slot.room_id, *key))
            if slot.student_group_id is not None:
                reserved["group"].add((slot.student_group_id, *key))
        return reserved
