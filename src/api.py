"""
FastAPI backend pour Music Source Separator v2.1
WITH: Monitoring, Structured Logging, Resilience Patterns
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request, Response
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import uuid
import asyncio
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from typing import Dict, Optional, Any
try:
    import redis
except Exception:
    redis = None
try:
    from opentelemetry import trace as otel_trace
except Exception:
    otel_trace = None
import soundfile as sf
import tempfile
import shutil
import time
from datetime import datetime
import threading
import os
from contextlib import contextmanager  # kept for potential future use (no pika import)


# Background metrics updater
_metrics_stop_event = threading.Event()
_metrics_thread: Optional[threading.Thread] = None
_METRICS_INTERVAL = int(os.environ.get("METRICS_PUBLISH_INTERVAL", "15"))

# Job management (in-memory). For higher scale, persist to Redis/DB.
JOBS: Dict[str, Dict] = {}
# Process pool for CPU-bound separation tasks — created at lifespan startup
_process_pool: Optional[ProcessPoolExecutor] = None
_PROCESS_POOL_MAX_WORKERS = int(os.environ.get("PROCESS_POOL_WORKERS", "2"))

# Redis / Celery config
REDIS_URL = os.environ.get("REDIS_URL", None)
MAX_PENDING = int(os.environ.get("MAX_PENDING", "4"))
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "100"))
MAX_DURATION_SECONDS = int(os.environ.get("MAX_DURATION_SECONDS", "600"))

_redis_client: Optional[Any] = None
USE_CELERY = False
if REDIS_URL and redis is not None:
    try:
        tmp_redis = redis.from_url(REDIS_URL)
        # quick ping
        tmp_redis.ping()
        _redis_client = tmp_redis
        USE_CELERY = True
    except Exception:
        USE_CELERY = False
else:
    USE_CELERY = False


# ✅ Import stems config
from src.stems import STEM_CONFIGS
from src.separator import get_separator, clear_cache, MusicSeparator, get_best_device

# ✅ Import monitoring and resilience
from src.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    separations_total,
    separation_duration_seconds,
    separation_file_size_bytes,
    errors_total,
    models_loaded,
    update_system_metrics,
    update_temp_storage_metrics,
    get_metrics,
    get_metrics_content_type
)
from src.metrics import (
    running_jobs,
    pending_jobs,
    process_pool_busy,
    process_pool_workers,
    active_sessions,
)
from src.logging_config import (
    setup_logging,
    get_logger,
    log_request,
    log_separation,
    log_error
)
from src.resilience import (
    retry,
    CircuitBreaker,
    RateLimiter,
    CircuitBreakerOpen,
    RateLimitExceeded,
    RetryExhausted
)

if USE_CELERY:
    try:
        from src.celery_app import celery  # noqa: F401
        from src.tasks import separate_task  # noqa: F401
    except Exception:
        USE_CELERY = False


def _worker_separate(model_name: str, input_path: str, output_dir: str) -> Dict[str, str]:
    """Worker function executed in a separate process to load model and run separation.
    Must be top-level so it is picklable for ProcessPoolExecutor.
    """
    # Import inside worker process to avoid issues with pickling model objects
    from src.separator import MusicSeparator

    separator = MusicSeparator(model_name=model_name)
    return separator.separate(str(input_path), str(output_dir))

# ✅ Setup structured logging
setup_logging(level="INFO", json_format=True)
logger = get_logger(__name__)

# ✅ Create resilience components
model_circuit_breaker = CircuitBreaker(
    failure_threshold=3,
    timeout=60.0
)

api_rate_limiter = RateLimiter(
    max_requests=10,
    window_seconds=60  # 10 requests per minute per IP
)

# Créer l'application FastAPI
app = FastAPI(
    title="Music Source Separator API v2.1",
    description="Sépare les pistes audio avec Demucs et MVSEP - WITH Monitoring",
    version="2.1.0"
)

# CORS pour Gradio
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dossier temporaire pour les résultats
TEMP_DIR = Path("/tmp/music-separator")
TEMP_DIR.mkdir(exist_ok=True)


# ============================================================
# MIDDLEWARE
# ============================================================

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Middleware to track all HTTP requests with metrics"""
    start_time = time.time()

    # Respect incoming X-Request-ID if present (propagate), otherwise generate
    incoming_req_id = request.headers.get("x-request-id") or request.headers.get("X-Request-ID")
    request_id = incoming_req_id if incoming_req_id else uuid.uuid4().hex

    # Try to extract trace_id from OpenTelemetry if available
    trace_id = None
    try:
        if otel_trace is not None:
            span = otel_trace.get_current_span()
            if span is not None:
                ctx = span.get_span_context()
                if ctx is not None and getattr(ctx, "trace_id", 0):
                    trace_id = f"{ctx.trace_id:032x}"
    except Exception:
        trace_id = None

    # Attach ids to request.state for handlers
    request.state.request_id = request_id
    request.state.trace_id = trace_id

    # Create logger with context
    ctx = {"request_id": request_id}
    if trace_id:
        ctx["trace_id"] = trace_id
    request_logger = get_logger(__name__, ctx)

    status: int = 500  # Default status
    response = None
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception as e:
        status = 500
        log_error(request_logger, e, context=str(request.url))
        raise
    finally:
        duration = time.time() - start_time
        
        # Update Prometheus metrics
        http_requests_total.labels(
            method=request.method,
            endpoint=request.url.path,
            status=status
        ).inc()
        
        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)
        
        # Structured logging
        log_request(
            request_logger,
            method=request.method,
            endpoint=str(request.url.path),
            status=status,
            duration=duration,
            client_ip=request.client.host if request.client else "unknown"
        )
        # Ensure request id is propagated back in response headers
        try:
            if response is not None:
                response.headers.setdefault("X-Request-ID", request_id)
                if trace_id:
                    response.headers.setdefault("X-Trace-ID", trace_id)
        except Exception:
            # ignore header failures
            pass

    return response


# Créer l'application FastAPI 
@app.get("/")
def root():
    """Page d'accueil"""
    return {
        "name": "Music Source Separator API",
        "version": "2.1.0",
        "status": "operational",
        "features": ["monitoring", "structured_logging", "resilience"],
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "metrics": "/metrics",
            "models": "/models",
            "separate": "/separate"
        }
    }


@app.get("/health")
def health_check():
    """Health check endpoint with detailed system info"""
    import torch
    
    device = get_best_device()
    device_info = {
        "current": device,
        "cuda_available": torch.cuda.is_available(),
        "mps_available": (
            hasattr(torch.backends, 'mps') and 
            torch.backends.mps.is_available() 
            if hasattr(torch.backends, 'mps') 
            else False
        ),
    }
    
    # Get loaded models count
    loaded_models = list(get_separator.__globals__.get('_loaded_models', {}).keys())
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "device": device,
        "device_info": device_info,
        "models_loaded": loaded_models,
        "models_loaded_count": len(loaded_models),
        "circuit_breaker_state": model_circuit_breaker.state,
        "temp_dir": str(TEMP_DIR),
        "temp_dir_exists": TEMP_DIR.exists()
    }


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint"""
    update_system_metrics()
    update_temp_storage_metrics(str(TEMP_DIR))
    
    return Response(
        content=get_metrics(),
        media_type=get_metrics_content_type()
    )


@app.get("/models")
def get_models():
    """Liste des modèles disponibles avec détails"""
    models_info = MusicSeparator.get_available_models()
    
    logger.info("Models list requested", extra={"models_count": len(models_info)})
    
    return {
        "models": list(models_info.keys()),
        "total": len(models_info),
        "details": models_info
    }


@app.get("/models/{model_name}")
def get_model_info(model_name: str):
    """Info sur un modèle spécifique"""
    try:
        info = MusicSeparator.get_model_info(model_name)
        logger.info(f"Model info requested: {model_name}")
        return info
    except ValueError as e:
        logger.warning(f"Model not found: {model_name}")
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/separate")
async def separate_audio(
    request: Request,
    file: UploadFile = File(...),
    demucs_model: str = Form(default="htdemucs_6s", alias="model_name")
):
    """
    Sépare un fichier audio en stems
    WITH: Metrics, structured logging, rate limiting, circuit breaker

    Args:
        file: Fichier audio (WAV, MP3, FLAC, etc.)
        model_name: Modèle à utiliser (htdemucs_6s, htdemucs_ft, etc.)

    Returns:
        JSON avec chemins des stems générés

    Raises:
        HTTPException: Si le modèle n'existe pas ou erreur pendant la séparation
    """
    start_time = time.time()
    
    # Get client IP for rate limiting
    client_ip = request.client.host if request.client else "unknown"
    
    # ✅ Rate limiting
    try:
        if not api_rate_limiter._allow_request(client_ip):
            remaining = api_rate_limiter.get_remaining(client_ip)
            logger.warning(
                f"Rate limit exceeded for {client_ip}",
                extra={"client_ip": client_ip, "remaining": remaining}
            )
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again later. ({remaining} requests remaining)"
            )
    except RateLimitExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))
    
    logger.info(
        f"Separation request",
        extra={
            "model": demucs_model,
            "uploaded_filename": file.filename,
            "client_ip": client_ip
        }
    )

    # ✅ Check model exists
    if demucs_model not in STEM_CONFIGS.keys():
        available = list(STEM_CONFIGS.keys())
        errors_total.labels(
            type="InvalidModel",
            endpoint="/separate"
        ).inc()
        raise HTTPException(
            status_code=400,
            detail=f"Modèle '{demucs_model}' non disponible. "
                   f"Modèles disponibles: {available}"
        )
    # Respect circuit breaker state: reject new jobs if open
    if getattr(model_circuit_breaker, "state", None) == "open":
        logger.error("Circuit breaker open - rejecting new separation requests")
        raise HTTPException(status_code=503, detail="Model service temporarily unavailable. Try again later.")
    
    # Créer un dossier temporaire unique
    temp_session = tempfile.mkdtemp(dir=TEMP_DIR)
    temp_path = Path(temp_session)

    try:
        # Sauvegarder le fichier uploadé sur disque sans tout charger en mémoire
        input_file = temp_path / "input.wav"

        def _save_upload_sync(upload: UploadFile, dest_path: str) -> int:
            upload.file.seek(0)
            with open(dest_path, "wb") as dest:
                shutil.copyfileobj(upload.file, dest)
            return os.path.getsize(dest_path)

        loop = asyncio.get_running_loop()
        try:
            file_size = await loop.run_in_executor(None, _save_upload_sync, file, str(input_file))
        except Exception as e:
            logger.error("Failed to save upload", extra={"error": str(e)})
            raise HTTPException(status_code=500, detail="Failed to save uploaded file")

        # Track file size
        separation_file_size_bytes.observe(file_size)

        logger.info(
            f"File saved",
            extra={"file_path": str(input_file), "file_size_bytes": file_size, "session_id": temp_path.name}
        )

        # Créer le dossier de sortie
        output_dir = temp_path / "output"
        output_dir.mkdir(exist_ok=True)

        # Validate file duration (avoid huge jobs)
        try:
            info = sf.info(str(input_file))
            duration_seconds = float(info.frames) / float(info.samplerate)
        except Exception:
            duration_seconds = None

        if duration_seconds is not None and duration_seconds > MAX_DURATION_SECONDS:
            shutil.rmtree(temp_path, ignore_errors=True)
            raise HTTPException(status_code=413, detail=f"Audio duration {duration_seconds:.0f}s exceeds maximum allowed {MAX_DURATION_SECONDS}s")

        # Validate file size
        max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
        if file_size > max_bytes:
            shutil.rmtree(temp_path, ignore_errors=True)
            raise HTTPException(status_code=413, detail=f"File size {file_size} bytes exceeds maximum allowed {max_bytes} bytes")

        now_ts = time.time()

        # If using Celery+Redis, enforce MAX_PENDING via Redis counter
        if USE_CELERY and _redis_client is not None:
            counter_key = "music_separator:running"
            try:
                current_running = int(_redis_client.get(counter_key) or 0)
            except Exception:
                current_running = 0

            if current_running >= MAX_PENDING:
                shutil.rmtree(temp_path, ignore_errors=True)
                raise HTTPException(status_code=429, detail="System busy, try again later")

            # Submit to Celery
            try:
                from src.celery_app import celery

                # Increment pending_jobs gauge to reflect queued task
                try:
                    pending_jobs.inc()
                except Exception:
                    pass

                async_result = celery.send_task("src.tasks.separate_task", args=[demucs_model, str(input_file), str(output_dir)])
                job_id = async_result.id
                JOBS[job_id] = {
                    "status": "pending",
                    "model": demucs_model,
                    "session_id": temp_path.name,
                    "submitted_at": now_ts,
                    "started_at": None,
                    "finished_at": None,
                    "result": None,
                    "error": None,
                    "file_size": file_size,
                    "output_dir": str(output_dir),
                    "celery_id": async_result.id,
                }

                return {
                    "status": "accepted",
                    "job_id": job_id,
                    "session_id": temp_path.name,
                    "status_url": f"/status/{job_id}",
                    "download_template": f"/download/status/{job_id}/{{stem_name}}"
                }
            except Exception as e:
                logger.error(f"Failed to submit Celery task: {e}")
                shutil.rmtree(temp_path, ignore_errors=True)
                raise HTTPException(status_code=500, detail="Failed to schedule job")

        # Fallback: submit to local process pool
        if _process_pool is None:
            logger.error("Process pool not available")
            raise HTTPException(status_code=503, detail="Processing back-end not available")

        job_id = uuid.uuid4().hex
        JOBS[job_id] = {
            "status": "pending",
            "model": demucs_model,
            "session_id": temp_path.name,
            "submitted_at": now_ts,
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "file_size": file_size,
            "output_dir": str(output_dir)
        }

        # Submit the worker to process pool
        def _on_done(fut, job_id=job_id, model=demucs_model):
            JOBS[job_id]["finished_at"] = time.time()
            try:
                res = fut.result()
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["result"] = res

                # Update metrics
                separations_total.labels(model=model, status="success").inc()
                duration = JOBS[job_id]["finished_at"] - (JOBS[job_id]["started_at"] or JOBS[job_id]["submitted_at"])
                try:
                    separation_duration_seconds.labels(model=model).observe(duration)
                except Exception:
                    logger.debug("Could not observe separation duration metric")

                # Log
                log_separation(
                    logger,
                    model=model,
                    audio_duration=duration,
                    processing_duration=duration,
                    status="success",
                    session_id=JOBS[job_id]["session_id"],
                    stems_count=len(res) if res else 0,
                    file_size_bytes=JOBS[job_id]["file_size"]
                )
            except Exception as e:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["error"] = str(e)
                separations_total.labels(model=model, status="error").inc()
                errors_total.labels(type=type(e).__name__, endpoint="/separate").inc()
                logger.error("Job failed", extra={"job_id": job_id, "error": str(e)}, exc_info=True)
            finally:
                # Update process-pool metrics to reflect job completion
                try:
                    process_pool_busy.dec()
                except Exception:
                    pass
                try:
                    running_jobs.dec()
                except Exception:
                    pass

        # mark started and submit
        JOBS[job_id]["status"] = "running"
        JOBS[job_id]["started_at"] = time.time()
        # Update local process-pool metrics
        try:
            process_pool_busy.inc()
        except Exception:
            pass
        try:
            running_jobs.inc()
        except Exception:
            pass
        future = _process_pool.submit(_worker_separate, demucs_model, str(input_file), str(output_dir))
        JOBS[job_id]["future"] = future
        future.add_done_callback(_on_done)

        # Return job id and quick links
        return {
            "status": "accepted",
            "job_id": job_id,
            "session_id": temp_path.name,
            "status_url": f"/status/{job_id}",
            "download_template": f"/download/status/{job_id}/{{stem_name}}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scheduling separation job: {e}", exc_info=True)
        shutil.rmtree(temp_path, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{session_id}/{stem_name}")
def download_stem(session_id: str, stem_name: str):
    """
    Télécharge un stem spécifique
    """
    file_path = TEMP_DIR / session_id / "output" / f"{stem_name}.wav"
    
    if not file_path.exists():
        logger.warning(
            f"Stem not found",
            extra={"session_id": session_id, "stem_name": stem_name}
        )
        raise HTTPException(
            status_code=404,
            detail=f"Fichier {stem_name}.wav non trouvé pour session {session_id}"
        )
    
    logger.info(
        f"Stem download",
        extra={"session_id": session_id, "stem_name": stem_name}
    )
    
    return FileResponse(
        path=str(file_path),
        media_type="audio/wav",
        filename=f"{stem_name}.wav"
    )


@app.get("/status/{job_id}")
def get_job_status(job_id: str):
    """Retourne l'état d'un job de séparation"""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # If Celery used, prefer AsyncResult state
    resp = {k: v for k, v in job.items() if k != "future"}
    if USE_CELERY and job.get("celery_id"):
        try:
            from src.celery_app import celery

            async_res = celery.AsyncResult(job.get("celery_id"))
            state = async_res.state
            if state == "PENDING":
                resp["status"] = "pending"
            elif state in ("STARTED", "RETRY"):
                resp["status"] = "running"
            elif state == "SUCCESS":
                resp["status"] = "done"
                try:
                    resp["result"] = async_res.result
                except Exception:
                    resp["result"] = None
            elif state == "FAILURE":
                resp["status"] = "error"
                try:
                    resp["error"] = str(async_res.result)
                except Exception:
                    resp["error"] = "task failure"
            else:
                resp["status"] = state.lower()
        except Exception:
            resp["status"] = job.get("status")

    return resp


@app.get("/download/status/{job_id}/{stem_name}")
def download_by_job(job_id: str, stem_name: str):
    """Télécharge un stem pour un job donné (nouvel endpoint compatible)."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # For Celery-backed jobs, consult task state
    if USE_CELERY and job.get("celery_id"):
        try:
            from src.celery_app import celery
            async_res = celery.AsyncResult(job.get("celery_id"))
            if async_res.state != "SUCCESS":
                raise HTTPException(status_code=409, detail=f"Job not finished (state={async_res.state})")
        except HTTPException:
            raise
        except Exception:
            # if we cannot query celery, fall back to stored status
            if job.get("status") != "done":
                raise HTTPException(status_code=409, detail=f"Job not finished (status={job.get('status')})")
    else:
        if job.get("status") != "done":
            raise HTTPException(status_code=409, detail=f"Job not finished (status={job.get('status')})")

    output_dir = job.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=500, detail="Job has no output directory")

    file_path = Path(output_dir) / f"{stem_name}.wav"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Stem not found for job")

    return FileResponse(path=str(file_path), media_type="audio/wav", filename=f"{stem_name}.wav")


@app.post("/clear-cache")
def clear_model_cache():
    """Vide le cache des modèles chargés en mémoire"""
    logger.info("Clearing model cache")
    clear_cache()
    
    return {
        "status": "success",
        "message": "Model cache cleared"
    }


@app.delete("/cleanup/{session_id}")
def cleanup_session(session_id: str):
    """Nettoie les fichiers temporaires d'une session"""
    session_path = TEMP_DIR / session_id
    
    if session_path.exists():
        logger.info(f"Cleaning up session", extra={"session_id": session_id})
        shutil.rmtree(session_path)
        return {
            "status": "success",
            "message": "Session cleaned",
            "session_id": session_id
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} non trouvée"
        )


@app.post("/cleanup-all")
def cleanup_all():
    """Nettoie TOUS les fichiers temporaires"""
    count = 0
    logger.warning("Cleaning up ALL sessions")
    
    try:
        for item in TEMP_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
                count += 1
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    logger.info(f"Cleaned sessions", extra={"sessions_removed": count})
    return {
        "status": "success",
        "message": f"Cleaned {count} sessions",
        "sessions_removed": count
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager to initialize process pool and background metrics thread.
    Replaces deprecated @app.on_event startup/shutdown.
    """
    logger.info("Music Separator API starting up (lifespan)")

    # Clear old temp files
    try:
        for item in TEMP_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
    except Exception as e:
        logger.error(f"Error cleaning temp dir on startup: {e}")

    logger.info(f"Device: {get_best_device()}")
    logger.info(f"Available models: {list(STEM_CONFIGS.keys())}")

    # Initial update of models_loaded metric (0 or currently loaded)
    try:
        loaded = list(get_separator.__globals__.get('_loaded_models', {}).keys())
        models_loaded.set(len(loaded))
    except Exception:
        logger.debug("Could not set initial models_loaded metric")

    # Start background thread to periodically refresh system/temp metrics and models_loaded
    global _metrics_thread, _metrics_stop_event, _process_pool
    _metrics_stop_event.clear()

    def _metrics_updater_loop():
        logger.info("Metrics updater thread started")
        while not _metrics_stop_event.is_set():
            try:
                update_system_metrics()
                update_temp_storage_metrics(str(TEMP_DIR))
                try:
                    loaded = list(get_separator.__globals__.get('_loaded_models', {}).keys())
                    models_loaded.set(len(loaded))
                except Exception:
                    logger.debug("Could not update models_loaded in metrics loop")
            except Exception as e:
                logger.error(f"Error updating metrics in background thread: {e}")
            _metrics_stop_event.wait(_METRICS_INTERVAL)
        logger.info("Metrics updater thread stopped")

    if _metrics_thread is None or not _metrics_thread.is_alive():
        _metrics_thread = threading.Thread(target=_metrics_updater_loop, name="metrics_updater", daemon=True)
        _metrics_thread.start()

    # Create process pool for CPU-bound separation tasks
    try:
        _process_pool = ProcessPoolExecutor(max_workers=_PROCESS_POOL_MAX_WORKERS)
        logger.info(f"ProcessPoolExecutor started with {_PROCESS_POOL_MAX_WORKERS} workers")
        try:
            process_pool_workers.set(_PROCESS_POOL_MAX_WORKERS)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Could not start process pool: {e}")
        _process_pool = None

    try:
        yield
    finally:
        logger.info("Music Separator API shutting down (lifespan)")
        # Stop metrics thread
        try:
            _metrics_stop_event.set()
            if _metrics_thread is not None:
                _metrics_thread.join(timeout=5)
        except Exception as e:
            logger.error(f"Error stopping metrics thread: {e}")

        # Shutdown process pool
        try:
            if _process_pool is not None:
                _process_pool.shutdown(wait=True)
                logger.info("Process pool shut down")
        except Exception as e:
            logger.error(f"Error shutting down process pool: {e}")


# Attach lifespan to app
app.router.lifespan_context = lifespan


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)