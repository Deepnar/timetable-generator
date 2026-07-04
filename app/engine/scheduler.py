from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
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
    3. Loads cross-timetable conflicts from PUBLISHED instances
    4. Runs solver N times for N instances
    5. Saves all slots to DB
    6. Updates generation status
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
            instances_requested=instances_requested,
            algorithm=algorithm,
            triggered_by=triggered_by,
            status=GenerationStatus.PENDING
        )
        self.db.add(generation)
        self.db.flush()

        # Load cross-timetable conflicts (slots already published)
        reserved_conflicts = self._load_published_conflicts()

        generation.status = GenerationStatus.RUNNING
        self.db.flush()

        instances_created = 0
        
        for _ in range(instances_requested):
            instance = TimetableInstance(
                generation_id=generation.id,
                status=InstanceStatus.DRAFT
            )
            self.db.add(instance)
            self.db.flush()

            # Run solver
            solver = GreedySolver(
                db=self.db,
                profile_id=profile_id,
                instance_id=instance.id
            )
            
            # Inject reserved conflicts into the solver
            solver.reserved_conflicts = reserved_conflicts

            slots = solver.solve()
            
            for slot in slots:
                self.db.add(slot)
            
            instances_created += 1

        generation.status = GenerationStatus.COMPLETED
        generation.instances_generated = instances_created
        generation.completed_at = datetime.now()
        self.db.commit()

        return generation

    def _load_published_conflicts(self):
        """
        Fetches all slots from PUBLISHED timetable instances.
        Returns a set of (faculty_id, room_id, group_id, day_of_week, slot_number) tuples
        representing times that are absolutely booked and cannot be touched by new runs.
        """
        # Find all published instances across ALL generations
        published_ids = self.db.scalars(
            select(TimetableInstance.id).where(
                TimetableInstance.status == InstanceStatus.PUBLISHED
            )
        ).all()

        if not published_ids:
            return set()

        # Load their slots
        published_slots = self.db.scalars(
            select(TimetableSlot).where(
                TimetableSlot.instance_id.in_(published_ids)
            )
        ).all()

        reserved = set()
        for slot in published_slots:
            reserved.add((
                slot.faculty_id, 
                slot.room_id, 
                slot.student_group_id, 
                slot.day_of_week, 
                slot.slot_number
            ))
        
        return reserved
