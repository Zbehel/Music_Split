from .celery_app import celery
from src.metrics import running_jobs, pending_jobs
import os
import traceback
import redis

from celery import states


@celery.task(bind=True)
def separate_task(self, model_name: str, input_path: str, output_dir: str):
    """Celery task that runs separation using MusicSeparator.
    It stores results on disk and returns a dict of stem->path.
    Increments/decrements a Redis counter to track running jobs.
    """
    # Redis used for simple running counter
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = redis.from_url(redis_url)
    counter_key = "music_separator:running"

    try:
        # increment running (redis counter already used for cross-process accounting)
        try:
            r.incr(counter_key)
        except Exception:
            pass
        # Update Prometheus metric for running jobs when possible
        try:
            running_jobs.inc()
        except Exception:
            pass
        # If we tracked pending_jobs on submission, decrement here as the task starts
        try:
            pending_jobs.dec()
        except Exception:
            pass

        # Lazy import to avoid heavy imports at module import time
        from src.separator import MusicSeparator

        separator = MusicSeparator(model_name=model_name)
        res = separator.separate(str(input_path), str(output_dir))
        return res
    except Exception as e:
        # store traceback for diagnostics
        tb = traceback.format_exc()
        raise self.retry(exc=e, countdown=5, max_retries=1)
    finally:
        try:
            r.decr(counter_key)
        except Exception:
            pass
        try:
            running_jobs.dec()
        except Exception:
            pass
