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
import threading
import os
from contextlib import contextmanager  # kept for potential future use (no pika import)
import yt_dlp
import subprocess



# Background metrics updater
_metrics_stop_event = threading.Event()
_metrics_thread: Optional[threading.Thread] = None
_METRICS_INTERVAL = int(os.environ.get("METRICS_PUBLISH_INTERVAL", "15"))

import json
from pathlib import Path


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


def _worker_separate(model_name: str, input_path: str, output_dir: str, device: Optional[str] = None) -> Dict[str, str]:
    """Worker function executed in a separate process to load model and run separation.
    Must be top-level so it is picklable for ProcessPoolExecutor.
    """
    # Import inside worker process to avoid issues with pickling model objects
    from src.separator import MusicSeparator

    separator = MusicSeparator(model_name=model_name, device=device)
    return separator.separate(str(input_path), str(output_dir))

def download_youtube_audio(url: str, output_dir: Path) -> Path:
    """Downloads audio from YouTube URL to output_dir/input.wav"""
    output_template = str(output_dir / "input.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        # Use OAuth2 for authentication to bypass bot detection
        'username': 'oauth2',
        'password': '',
    }
    
    # Check for cookies.txt in current directory or secrets
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = "cookies.txt"
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
        
    # Find the file (it might be input.wav)
    if (output_dir / "input.wav").exists():
        return output_dir / "input.wav"
    
    raise FileNotFoundError("YouTube download failed to produce input.wav")


# ✅ Setup structured logging
setup_logging(level="INFO", json_format=True)
logger = get_logger(__name__)

import json
from pathlib import Path

class JobManager:
    def __init__(self, persistence_dir: Optional[str] = None):
        self.persistence_dir = Path(persistence_dir) if persistence_dir else None
        self._memory_jobs = {}
        if self.persistence_dir:
            self.persistence_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"JobManager using persistence dir: {self.persistence_dir}")

    def _get_file_path(self, job_id: str) -> Path:
        return self.persistence_dir / f"{job_id}.json"

    def __getitem__(self, job_id: str) -> Dict:
        if self.persistence_dir:
            fpath = self._get_file_path(job_id)
            if fpath.exists():
                try:
                    with open(fpath, "r") as f:
                        data = json.load(f)
                        # Restore future if it was in memory (not persisted)
                        # Note: futures cannot be persisted. If we restart, future is lost.
                        # But status should be updated before future is done?
                        # If status is 'running' and we restarted, it's effectively 'failed' or 'lost'.
                        return data
                except Exception as e:
                    logger.error(f"Failed to load job {job_id}: {e}")
        return self._memory_jobs[job_id]

    def __setitem__(self, job_id: str, data: Dict):
        # Remove non-serializable objects for persistence
        persist_data = data.copy()
        if "future" in persist_data:
            del persist_data["future"]
        
        if self.persistence_dir:
            try:
                with open(self._get_file_path(job_id), "w") as f:
                    json.dump(persist_data, f)
            except Exception as e:
                logger.error(f"Failed to save job {job_id}: {e}")
        
        self._memory_jobs[job_id] = data

    def get(self, job_id: str, default=None):
        try:
            return self[job_id]
        except KeyError:
            return default

    def __contains__(self, job_id: str):
        if self.persistence_dir:
            return self._get_file_path(job_id).exists()
        return job_id in self._memory_jobs

# Job management
JOBS_DIR = os.environ.get("JOBS_DIR")
JOBS = JobManager(JOBS_DIR)

# Determine device for API (env override takes precedence)
ENV_DEVICE = os.environ.get("DEVICE") or os.environ.get("SELECTED_DEVICE")
if ENV_DEVICE and ENV_DEVICE.lower() != "auto":
    SELECTED_DEVICE = ENV_DEVICE
else:
    try:
        SELECTED_DEVICE = get_best_device()
    except Exception:
        SELECTED_DEVICE = "cpu"
logger.info(f"Selected device for API: {SELECTED_DEVICE}")

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


@app.get("/device")
def get_selected_device():
    """Return the device the API will use for separation jobs"""
    return {"device": SELECTED_DEVICE}


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
    model_name: str = Form(default="htdemucs_6s")
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
            "model": model_name,
            "uploaded_filename": file.filename,
            "client_ip": client_ip
        }
    )

    # ✅ Check model exists
    if model_name not in STEM_CONFIGS.keys():
        available = list(STEM_CONFIGS.keys())
        errors_total.labels(
            type="InvalidModel",
            endpoint="/separate"
        ).inc()
        raise HTTPException(
            status_code=400,
            detail=f"Modèle '{model_name}' non disponible. "
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

        # Celery check
        if USE_CELERY and _redis_client is not None:
             from src.celery_app import celery
             async_result = celery.send_task("src.tasks.separate_task", args=[model_name, str(input_file), str(output_dir), SELECTED_DEVICE])
             job_id = async_result.id
             JOBS[job_id] = {
                "status": "pending",
                "model": model_name,
                "device": SELECTED_DEVICE,
                "session_id": temp_path.name,
                "submitted_at": now_ts,
                "started_at": None,
                "finished_at": None,
                "result": None,
                "error": None,
                "file_size": file_size,
                "output_dir": str(output_dir),
                "celery_id": async_result.id,
                "source": "upload"
            }
             return {
                "status": "accepted",
                "job_id": job_id,
                "session_id": temp_path.name,
                "status_url": f"/status/{job_id}",
                "download_template": f"/download/status/{job_id}/{{stem_name}}"
            }

        # Local Pool Fallback
        if _process_pool is None:
             raise HTTPException(status_code=503, detail="Backend unavailable")

        job_id = uuid.uuid4().hex
        JOBS[job_id] = {
            "status": "pending",
            "model": model_name,
            "device": SELECTED_DEVICE,
            "session_id": temp_path.name,
            "submitted_at": now_ts,
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "file_size": file_size,
            "output_dir": str(output_dir),
            "source": "upload"
        }

        def _on_done(fut, job_id=job_id, model=model_name):
            JOBS[job_id]["finished_at"] = time.time()
            try:
                res = fut.result()
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["result"] = res
                separations_total.labels(model=model, status="success").inc()
            except Exception as e:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["error"] = str(e)
                separations_total.labels(model=model, status="error").inc()
            finally:
                 try:
                    process_pool_busy.dec()
                    running_jobs.dec()
                 except: pass

        JOBS[job_id]["status"] = "running"
        JOBS[job_id]["started_at"] = time.time()
        try:
            process_pool_busy.inc()
            running_jobs.inc()
        except: pass
        
        future = _process_pool.submit(_worker_separate, model_name, str(input_file), str(output_dir), SELECTED_DEVICE)
        JOBS[job_id]["future"] = future
        future.add_done_callback(_on_done)

        return {
            "status": "accepted",
            "job_id": job_id,
            "session_id": temp_path.name,
            "status_url": f"/status/{job_id}",
            "download_template": f"/download/status/{job_id}/{{stem_name}}"
        }

    except Exception as e:
        logger.error(f"Error scheduling separation job: {e}", exc_info=True)
        shutil.rmtree(temp_path, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


class YouTubeRequest(BaseModel):
    url: str
    model_name: str = "htdemucs_6s"

@app.post("/separate/youtube")
async def separate_youtube(request: Request, yt_req: YouTubeRequest):
    """
    Downloads YouTube audio and triggers separation.
    """
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    # Rate limiting
    try:
        if not api_rate_limiter._allow_request(client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    except RateLimitExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))

    # Check model
    if yt_req.model_name not in STEM_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Invalid model: {yt_req.model_name}")

    # Create temp session
    temp_session = tempfile.mkdtemp(dir=TEMP_DIR)
    temp_path = Path(temp_session)
    output_dir = temp_path / "output"
    output_dir.mkdir(exist_ok=True)

    try:
        # Download YouTube (sync, but fast enough for now, or could be async)
        loop = asyncio.get_running_loop()
        input_file = await loop.run_in_executor(None, download_youtube_audio, yt_req.url, temp_path)
        
        file_size = input_file.stat().st_size
        
        # --- Reuse logic from 
        
        now_ts = time.time()
        
        # Celery check
        if USE_CELERY and _redis_client is not None:
             # ... (Logic identical to /separate for Celery submission)
             from src.celery_app import celery
             async_result = celery.send_task("src.tasks.separate_task", args=[yt_req.model_name, str(input_file), str(output_dir), SELECTED_DEVICE])
             job_id = async_result.id
             JOBS[job_id] = {
                "status": "pending",
                "model": yt_req.model_name,
                "device": SELECTED_DEVICE,
                "session_id": temp_path.name,
                "submitted_at": now_ts,
                "started_at": None,
                "finished_at": None,
                "result": None,
                "error": None,
                "file_size": file_size,
                "output_dir": str(output_dir),
                "celery_id": async_result.id,
                "source": "youtube",
                "original_url": yt_req.url
            }
             return {
                "status": "accepted",
                "job_id": job_id,
                "session_id": temp_path.name,
                "status_url": f"/status/{job_id}",
            }

        # Local Pool Fallback
        if _process_pool is None:
             raise HTTPException(status_code=503, detail="Backend unavailable")

        job_id = uuid.uuid4().hex
        JOBS[job_id] = {
            "status": "pending",
            "model": yt_req.model_name,
            "device": SELECTED_DEVICE,
            "session_id": temp_path.name,
            "submitted_at": now_ts,
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "file_size": file_size,
            "output_dir": str(output_dir),
            "source": "youtube",
            "original_url": yt_req.url
        }

        def _on_done(fut, job_id=job_id, model=yt_req.model_name):
            JOBS[job_id]["finished_at"] = time.time()
            try:
                res = fut.result()
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["result"] = res
                separations_total.labels(model=model, status="success").inc()
            except Exception as e:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["error"] = str(e)
                separations_total.labels(model=model, status="error").inc()
            finally:
                 try:
                    process_pool_busy.dec()
                    running_jobs.dec()
                 except: pass

        JOBS[job_id]["status"] = "running"
        JOBS[job_id]["started_at"] = time.time()
        try:
            process_pool_busy.inc()
            running_jobs.inc()
        except: pass
        
        future = _process_pool.submit(_worker_separate, yt_req.model_name, str(input_file), str(output_dir), SELECTED_DEVICE)
        JOBS[job_id]["future"] = future
        future.add_done_callback(_on_done)

        return {
            "status": "accepted",
            "job_id": job_id,
            "session_id": temp_path.name,
            "status_url": f"/status/{job_id}",
        }

    except Exception as e:
        logger.error(f"YouTube separation failed: {e}")
        shutil.rmtree(temp_path, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


class MixRequest(BaseModel):
    session_id: str
    stems: Dict[str, float]  # stem_name -> volume (0.0 to 1.0)

@app.post("/mix")
def mix_stems(req: MixRequest):
    """
    Mixes selected stems into a single WAV file.
    """
    session_path = TEMP_DIR / req.session_id / "output"
    if not session_path.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    # Load and mix
    mixed_audio = None
    sr = 44100
    
    import numpy as np
    
    try:
        for stem_name, volume in req.stems.items():
            stem_path = session_path / f"{stem_name}.wav"
            if stem_path.exists() and volume > 0:
                data, rate = sf.read(str(stem_path), always_2d=True)
                sr = rate
                
                # Apply volume
                data = data * volume
                
                if mixed_audio is None:
                    mixed_audio = data
                else:
                    # Ensure lengths match (pad if needed)
                    if len(data) > len(mixed_audio):
                        # Pad mixed
                        pad = np.zeros((len(data) - len(mixed_audio), mixed_audio.shape[1]))
                        mixed_audio = np.vstack((mixed_audio, pad))
                    elif len(data) < len(mixed_audio):
                        # Pad data
                        pad = np.zeros((len(mixed_audio) - len(data), data.shape[1]))
                        data = np.vstack((data, pad))
                    
                    mixed_audio += data
        
        if mixed_audio is None:
             raise HTTPException(status_code=400, detail="No stems selected or found")

        # Normalize to prevent clipping
        max_val = np.max(np.abs(mixed_audio))
        if max_val > 1.0:
            mixed_audio = mixed_audio / max_val

        output_mix = session_path / "mix.wav"
        sf.write(str(output_mix), mixed_audio, sr)
        
        return FileResponse(
            path=str(output_mix),
            media_type="audio/wav",
            filename="mix.wav"
        )

    except Exception as e:
        logger.error(f"Mixing failed: {e}")
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


@app.get("/download/{session_id}/original")
def download_original(session_id: str):
    """
    Télécharge le fichier original (input.wav)
    """
    file_path = TEMP_DIR / session_id / "input.wav"
    
    if not file_path.exists():
        logger.warning(
            f"Original file not found",
            extra={"session_id": session_id}
        )
        raise HTTPException(
            status_code=404,
            detail=f"Fichier original non trouvé pour session {session_id}"
        )
    
    logger.info(
        f"Original download",
        extra={"session_id": session_id}
    )
    
    return FileResponse(
        path=str(file_path),
        media_type="audio/wav",
        filename="original.wav"
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