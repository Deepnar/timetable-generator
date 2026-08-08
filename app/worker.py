"""Celery application for background work (async generation).

Start the worker with::

    uv run celery -A app.worker:celery_app worker --loglevel=info

Tasks are discovered from ``app.tasks`` (the package is imported here so the
worker registers them). The API never imports this module directly — it only
talks to the tasks through ``app.tasks.generation`` — so starting the HTTP
server never connects to the broker.
"""
from celery import Celery

from app.config import settings

celery_app = Celery(
    "timetable",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.task_acks_late = True          # redeliver only on worker crash
celery_app.conf.worker_prefetch_multiplier = 1  # one generation at a time
celery_app.conf.broker_connection_retry_on_startup = True

celery_app.autodiscover_tasks(["app.tasks"])

# Ensure the task module is imported so the task is registered on this app
# (autodiscovery covers it, but an explicit import keeps `celery inspect` and
# unit tests that import the task directly consistent).
from app.tasks import generation as _generation_tasks  # noqa: E402, F401
