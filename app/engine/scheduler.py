from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.generation import (TimetableGeneration, TimetableInstance,
                                    TimetableSlot, GenerationStatus,
                                    InstanceStatus, AlgorithmType)
from app.models.profiles import TimetableProfile
from app.engine.solvers.greedy_solver import GreedySolver


class Scheduler:
    """
    Orchestrates the full generation run.
    1. Validates the profile exists
    2. Creates TimetableGeneration record
    3. Runs solver N times for N instances
    4. Saves all slots to DB
    5. Updates generation status
    """

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
        combination_id: int | None = None
    ) -> TimetableGeneration:

        # validate profile exists
        profile = self.db.scalars(
            select(TimetableProfile).where(
                TimetableProfile.id == profile_id,
                TimetableProfile.is_active == True
            )
        ).first()
        if not profile:
            raise ValueError(f"Profile {profile_id} not found or inactive")

        # create generation record
        generation = TimetableGeneration(
            profile_id=profile_id,
            combination_id=combination_id,
            academic_year=academic_year,
            semester=semester,
            timetable_type=timetable_type,
            generation_status=GenerationStatus.RUNNING,
            algorithm_used=algorithm,
            instances_requested=instances_requested,
            instances_produced=0,
            triggered_by=triggered_by,
            triggered_at=datetime.utcnow()
        )
        self.db.add(generation)
        self.db.commit()
        self.db.refresh(generation)

        try:
            instances_produced = 0
            best_score = 0.0

            for i in range(1, instances_requested + 1):
                instance = TimetableInstance(
                    generation_id=generation.id,
                    instance_number=i,
                    label=self._instance_label(i),
                    status=InstanceStatus.DRAFT,
                    hard_violations=0
                )
                self.db.add(instance)
                self.db.commit()
                self.db.refresh(instance)

                # run solver
                if algorithm == AlgorithmType.GREEDY:
                    solver = GreedySolver(
                        db=self.db,
                        profile_id=profile_id,
                        instance_id=instance.id
                    )
                    slots = solver.solve()
                else:
                    # OR-Tools comes later
                    # for now fall back to greedy
                    solver = GreedySolver(
                        db=self.db,
                        profile_id=profile_id,
                        instance_id=instance.id
                    )
                    slots = solver.solve()

                # save slots
                for slot in slots:
                    self.db.add(slot)
                self.db.commit()

                # score — for now just count slots placed
                score = float(len(slots))
                instance.soft_score = score
                if score > best_score:
                    best_score = score

                self.db.commit()
                instances_produced += 1

            # update generation record
            generation.generation_status = GenerationStatus.COMPLETED
            generation.instances_produced = instances_produced
            generation.score_best_instance = best_score
            generation.completed_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(generation)

        except Exception as e:
            generation.generation_status = GenerationStatus.FAILED
            generation.error_log = str(e)
            generation.completed_at = datetime.utcnow()
            self.db.commit()
            raise e

        return generation

    def _instance_label(self, number: int) -> str:
        labels = {
            1: "Best overall",
            2: "Balanced load",
            3: "Distributed spread"
        }
        return labels.get(number, f"Option {number}")