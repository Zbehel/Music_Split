from celery import Celery
import os

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "music_separator",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Optional: configure task serializer, result serializer
celery.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
