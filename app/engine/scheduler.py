"""Orchestrates the full timetable generation run.

Flow:
1. Validate the profile exists.
2. Create a ``TimetableGeneration`` record (status=PENDING).
3. Load cross-timetable conflicts from any PUBLISHED instance.
4. Run the solver N times for N candidate instances.
5. Save all slots and mark the run COMPLETED.
"""
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from app.models.generation import (
    TimetableGeneration,
    TimetableInstance,
    TimetableSlot,
    GenerationStatus,
    InstanceStatus,
    AlgorithmType,
)
from app.models.profiles import TimetableProfile
from app.models.constraints import SoftConstraint
from app.services.settings_service import get_settings
from app.engine.solvers.greedy_solver import GreedySolver
from app.engine.scorer import score_instance, ScoringContext


class Scheduler:
    """Coordinator between the API and the solver."""

    def __init__(self, db: Session):
        self.db = db

    def run(
        self,
        profile_id: int,
        timetable_type: str,
        academic_year: str,
        semester: int | None,
        instances_requested: int,
        algorithm: AlgorithmType,
        triggered_by: int,
        combination_id: int | None = None,
    ) -> TimetableGeneration:
        profile = self.db.scalars(
            select(TimetableProfile).where(
                TimetableProfile.id == profile_id,
                TimetableProfile.is_active == True,
            )
        ).first()
        if not profile:
            raise ValueError(f"Profile {profile_id} not found or inactive")

        generation = TimetableGeneration(
            profile_id=profile_id,
            combination_id=combination_id,
            academic_year=academic_year,
            semester=semester,
            timetable_type=timetable_type,
            instances_requested=instances_requested,
            algorithm_used=algorithm,
            triggered_by=triggered_by,
            generation_status=GenerationStatus.PENDING,
        )
        self.db.add(generation)
        self.db.flush()

        # Pre-load slots from every PUBLISHED instance, so the solver
        # can never double-book an already-live timetable.
        reserved_conflicts = self._load_published_conflicts()

        # Soft-constraint scoring (opt-in per college). When enabled, each
        # instance is scored so the admin can rank the candidates.
        settings = get_settings(self.db)
        soft_rules = (
            self._load_soft_constraints(profile_id)
            if settings.enable_soft_constraint_scoring
            else []
        )
        scoring_ctx = ScoringContext(self.db)

        generation.generation_status = GenerationStatus.RUNNING
        self.db.flush()

        instances_created = 0
        best_score: float | None = None
        for i in range(instances_requested):
            instance = TimetableInstance(
                generation_id=generation.id,
                instance_number=i + 1,
                status=InstanceStatus.DRAFT,
            )
            self.db.add(instance)
            self.db.flush()

            solver = self._make_solver(algorithm, profile_id, instance.id)
            solver.reserved_conflicts = reserved_conflicts

            slots = solver.solve()
            for slot in slots:
                self.db.add(slot)

            if soft_rules:
                score = score_instance(slots, soft_rules, scoring_ctx)
                instance.soft_score = score
                best_score = score if best_score is None else max(best_score, score)

            instances_created += 1

        generation.generation_status = GenerationStatus.COMPLETED
        generation.instances_produced = instances_created
        generation.score_best_instance = best_score
        generation.completed_at = datetime.utcnow()
        self.db.commit()

        return generation

    def _make_solver(self, algorithm: AlgorithmType, profile_id: int, instance_id: int):
        """Pick the solver for the requested algorithm (defaults to greedy)."""
        if algorithm == AlgorithmType.OR_TOOLS:
            # Lazy import so the heavy ortools dependency is only loaded when used.
            from app.engine.solvers.or_tools_solver import ORToolsSolver
            return ORToolsSolver(
                db=self.db, profile_id=profile_id, instance_id=instance_id
            )
        return GreedySolver(
            db=self.db, profile_id=profile_id, instance_id=instance_id
        )

    def _load_soft_constraints(self, profile_id: int) -> list[SoftConstraint]:
        """Active soft constraints for this profile plus any global ones."""
        return self.db.scalars(
            select(SoftConstraint).where(
                SoftConstraint.is_active == True,
                or_(
                    SoftConstraint.profile_id == profile_id,
                    SoftConstraint.profile_id.is_(None),
                ),
            )
        ).all()

    def _load_published_conflicts(self) -> dict[str, set[tuple]]:
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
        """
        reserved: dict[str, set[tuple]] = {
            "faculty": set(),
            "room": set(),
            "group": set(),
        }
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
            key = (slot.day_of_week, slot.slot_number)
            if slot.faculty_id is not None:
                reserved["faculty"].add((slot.faculty_id, *key))
            if slot.room_id is not None:
                reserved["room"].add((slot.room_id, *key))
            if slot.student_group_id is not None:
                reserved["group"].add((slot.student_group_id, *key))
        return reserved
