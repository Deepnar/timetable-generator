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
  PENDING run row so the API can return a ``run_id`` immediately.
* ``solve_generation()`` — load a run by id, solve it, and flip the row to
  COMPLETED (or FAILED with ``error_log``), stamping ``run_duration_ms``.
"""
import time
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.generation import (
    TimetableGeneration,
    TimetableInstance,
    TimetableSlot,
    GenerationStatus,
    InstanceStatus,
    AlgorithmType,
    VariationMode,
)
from app.services.settings_service import get_settings
from app.services import redis_client
from app.models.profiles import ResourceType
from app.engine.profile_resolver import ProfileResolver
from app.engine.solvers.greedy_solver import GreedySolver
from app.engine.scorer import score_instance, ScoringContext


class GenerationLockError(RuntimeError):
    """Raised when a generation cannot run because another run is already
    solving the same resources. The run row is marked FAILED before raising."""


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
        variation = generation.variation
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
                attempts.append((candidate, candidate_sig, score))
                is_distinct = all(
                    self._hamming(candidate_sig, prev)
                    >= self._DIVERSITY_MIN_DISTANCE
                    for prev in accepted_signatures
                )
                if variation != VariationMode.BEST and is_distinct:
                    break

            if variation == VariationMode.BEST:
                distinct = [
                    (c, sig, sc) for c, sig, sc in attempts
                    if all(
                        self._hamming(sig, prev) >= self._DIVERSITY_MIN_DISTANCE
                        for prev in accepted_signatures
                    )
                ]
                pool = distinct or attempts
                if soft_rules:
                    slots, signature, score = max(
                        pool, key=lambda t: t[2]
                    )
                else:
                    slots, signature, score = pool[0]
            else:
                slots, signature, score = attempts[-1]

            accepted_signatures.append(signature)
            for slot in slots:
                self.db.add(slot)

            if score is not None:
                instance.soft_score = score
                best_score = score if best_score is None else max(best_score, score)

            instances_created += 1

        generation.generation_status = GenerationStatus.COMPLETED
        generation.instances_produced = instances_created
        generation.score_best_instance = best_score
        generation.completed_at = datetime.utcnow()
        generation.run_duration_ms = int((time.time() - start) * 1000)
        self.db.commit()

        return generation

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

    def _load_published_conflicts(
        self, exempt_groups: set[int] | None = None
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

        ``exempt_groups``: groups whose published slots are NOT reserved. An
        exam generation passes its own groups here — a branch on exams has
        suspended its classes, so its published class slots (teacher, room,
        group) are free for the exam to reuse, while every other branch's
        active classes stay protected.
        """
        reserved: dict[str, set[tuple]] = {
            "faculty": set(),
            "room": set(),
            "group": set(),
        }
        exempt = set(exempt_groups or ())
        published_ids = self.db.scalars(
            select(TimetableInstance.id).where(
                TimetableInstance.status == InstanceStatus.PUBLISHED
            )
        ).all()
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
            if slot.room_id is not None:
                reserved["room"].add((slot.room_id, *key))
            if slot.student_group_id is not None:
                reserved["group"].add((slot.student_group_id, *key))
        return reserved
