"""
Celery application bootstrap.

Actual background jobs (RFM calculation, segmentation, product
similarity, FBT mining, model training, cache refresh) are added
starting Phase 3. This module exists in Phase 1 so `docker compose up`
brings up a working worker container and `flower` monitoring from day one.
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "ai_personalization",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


@celery_app.task(name="app.workers.celery_app.health_check_task")
def health_check_task() -> str:
    return "ok"
