"""Celery task that executes a generation run in the background.

The async ``POST /generate`` flow is:

1. The router validates the input contract and persists a ``PENDING`` run row
   via ``Scheduler.create_generation()``, so the client gets a ``run_id``
   immediately.
2. ``enqueue_generation(run_id)`` pushes this task to the broker.
3. The worker opens its own DB session and calls ``Scheduler.solve_generation()``,
   which re-resolves the profile from the run row, solves, and flips the row to
   ``COMPLETED`` (or ``FAILED`` with ``error_log``) and stamps ``run_duration_ms``.

The session factory is read from the ``app.database`` module at call time (not
imported by value) so the in-memory SQLite test suite's override is honoured.
"""
from celery import shared_task

from app import database
from app.engine.scheduler import Scheduler
from app.models.generation import TimetableGeneration, GenerationStatus


@shared_task(name="timetable.run_generation", acks_late=True)
def run_generation(run_id: int) -> None:
    """Execute one generation run. ``solve_generation`` records the outcome on
    the run row (COMPLETED, or FAILED + ``error_log``); the exception is
    swallowed here so an already-failed run is not redelivered and re-solved."""
    db = database.SessionLocal()
    try:
        generation = db.get(TimetableGeneration, run_id)
        if generation is None:
            return
        generation.generation_status = GenerationStatus.RUNNING
        db.commit()
        scheduler = Scheduler(db)
        try:
            scheduler.solve_generation(run_id)
        except Exception:
            pass
    finally:
        db.close()


def enqueue_generation(run_id: int) -> None:
    """Push a run to the broker. Raises if the broker is unreachable."""
    run_generation.delay(run_id)
