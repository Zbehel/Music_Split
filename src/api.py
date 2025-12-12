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
import multiprocessing
try:
    multiprocessing.set_start_method('spawn', force=True)
except RuntimeError:
    pass
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



# Custom FileResponse that disables range request support
class NoRangeFileResponse(FileResponse):
    """
    FileResponse that disables HTTP range request support.
    This ensures clients always receive the complete file (200 OK)
    instead of partial content (206 Partial Content).
    """
    async def __call__(self, scope, receive, send):
        # Remove Range header from request to prevent partial content
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            # Remove range header if present
            headers_to_remove = [b"range", b"Range"]
            scope["headers"] = [
                (name, value) for name, value in scope.get("headers", [])
                if name not in headers_to_remove
            ]
        
        # Call parent with modified scope
        await super().__call__(scope, receive, send)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set Accept-Ranges header to indicate we don't support range requests
        self.headers["Accept-Ranges"] = "none"


# Background metrics updater
_metrics_stop_event = threading.Event()
_metrics_thread: Optional[threading.Thread] = None
_METRICS_INTERVAL = int(os.environ.get("METRICS_PUBLISH_INTERVAL", "15"))

import json
from pathlib import Path


# Process pool for CPU-bound separation tasks — created at lifespan startup
_process_pool: Optional[ProcessPoolExecutor] = None
_PROCESS_POOL_MAX_WORKERS = int(os.environ.get("PROCESS_POOL_WORKERS", "1")) # Force 1 worker for stability

def _restart_process_pool():
    """Restarts the process pool if it's broken."""
    global _process_pool
    logger.warning("♻️ Restarting Process Pool...")
    try:
        if _process_pool:
            _process_pool.shutdown(wait=False)
    except Exception:
        pass
    
    try:
        _process_pool = ProcessPoolExecutor(max_workers=_PROCESS_POOL_MAX_WORKERS)
        logger.info("✅ Process Pool Restarted")
    except Exception as e:
        logger.error(f"❌ Failed to restart process pool: {e}")

MAX_PENDING = int(os.environ.get("MAX_PENDING", "4"))
MAX_DURATION_SECONDS = int(os.environ.get("MAX_DURATION_SECONDS", "600"))


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


def _worker_separate(model_name: str, input_path: str, output_dir: str, device: Optional[str] = None) -> Dict[str, str]:
    """Worker function executed in a separate process to load model and run separation.
    Must be top-level so it is picklable for ProcessPoolExecutor.
    """
    print(f"[Worker] Starting separation for {input_path} on {device}...")
    try:
        # Import inside worker process to avoid issues with pickling model objects
        from src.separator import MusicSeparator
        import torch
        
        print(f"[Worker] Imports done. Torch version: {torch.__version__}, CUDA: {torch.cuda.is_available()}")

        print(f"[Worker] Initializing MusicSeparator with model={model_name}...")
        separator = MusicSeparator(model_name=model_name, device=device)
        
        print(f"[Worker] Starting separator.separate()...")
        result = separator.separate(str(input_path), str(output_dir))
        
        print(f"[Worker] Separation finished successfully. Result: {list(result.keys())}")
        return result
    except Exception as e:
        print(f"[Worker] CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise e

def cleanup_old_sessions(max_age_seconds: int = 3600, max_to_check: int = 50):
    """
    Clean up old session directories (limited to prevent slowdown).
    
    Args:
        max_age_seconds: Delete sessions older than this (default 1 hour)
        max_to_check: Maximum number of sessions to check per call
    
    Returns:
        Number of sessions cleaned
    """
    try:
        sessions = list(TEMP_DIR.iterdir())
        # Sort by modification time, oldest first
        sessions.sort(key=lambda p: p.stat().st_mtime if p.is_dir() else 0)
        
        cleaned = 0
        checked = 0
        now = time.time()
        
        for session_dir in sessions:
            if checked >= max_to_check:
                break
            
            if session_dir.is_dir():
                checked += 1
                age_seconds = now - session_dir.stat().st_mtime
                if age_seconds > max_age_seconds:
                    shutil.rmtree(session_dir, ignore_errors=True)
                    cleaned += 1
                    logger.debug(f"Cleaned up old session: {session_dir.name}")
        
        if cleaned > 0:
            logger.info(f"Cleanup removed {cleaned} old sessions (checked {checked})")
        return cleaned
    except Exception as e:
        logger.warning(f"Failed to cleanup old sessions: {e}")
        return 0



def _commit_modal_volume():
    """Helper to commit changes to the Modal volume."""
    try:
        import modal
        # Use from_name to get the volume handle
        if hasattr(modal, "Volume"):
             vol = modal.Volume.from_name("music-split-jobs-data", create_if_missing=False)
             if vol:
                 vol.commit()
                 logger.debug("✅ Modal volume committed")
    except Exception as e:
        # Don't let volume commit failure break the app
        logger.warning(f"⚠️ Failed to commit Modal volume: {e}")


def download_youtube_audio(url: str, output_dir: Path) -> Path:
    """Downloads audio from YouTube URL to output_dir/input.wav"""
    
    # Configuration yt-dlp optimisée pour éviter les blocages
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_dir / 'input.%(ext)s'), # Force fixed filename for predictability
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        # Use default client with cookies
        # 'extractor_args': {
        #     'youtube': {
        #         'player_client': ['android', 'web'],
        #     }
        # },
        # Postprocessor to convert to WAV
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        # Fallback to cookies if available
        'cookiefile': '/data/youtube_cookies.txt' if Path('/data/youtube_cookies.txt').exists() else None,
        'nocheckcertificate': True,
    }
    
    if ydl_opts['cookiefile']:
        logger.info("Using YouTube cookies for authentication")
    else:
        logger.warning("No YouTube cookies found - downloads may fail for restricted videos")
    
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
    
    def values(self):
        """Return all job values (for iteration)"""
        # Return jobs from memory (includes both persisted and non-persisted)
        return self._memory_jobs.values()

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
    description="Sépare les pistes audio avec Demucs  - WITH Monitoring",
    version="2.1.0"
)

# CORS pour Gradio
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://music-split-frontend.pages.dev"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip compression for faster downloads
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Dossier temporaire pour les résultats
# Use /data/sessions for persistent storage on Modal (mounted volume)
# Falls back to /tmp/music-separator for local development
TEMP_DIR = Path(os.environ.get("SESSIONS_DIR", "/data/sessions")) if os.environ.get("JOBS_DIR") else Path("/tmp/music-separator")
TEMP_DIR.mkdir(exist_ok=True, parents=True)


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


class MixRequest(BaseModel):
    model_config = {"protected_namespaces": ()}  # Allow 'model_' prefix
    session_id: str
    stems: Dict[str, float]  # stem_name -> volume (0.0 to 1.0)

@app.post("/separate")
async def separate_audio(
    request: Request,
    file: UploadFile = File(...),
    separation_model: str = Form(default="htdemucs_6s", alias="model_name")
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
            "model": separation_model,
            "uploaded_filename": file.filename,
            "client_ip": client_ip
        }
    )

    # ✅ Check model exists
    if separation_model not in STEM_CONFIGS.keys():
        available = list(STEM_CONFIGS.keys())
        errors_total.labels(
            type="InvalidModel",
            endpoint="/separate"
        ).inc()
        raise HTTPException(
            status_code=400,
            detail=f"Modèle '{separation_model}' non disponible. "
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
        except Exception as e:
            logger.warning(f"Could not determine audio duration: {e}")
            duration_seconds = None

        # Log duration check for debugging
        if duration_seconds is not None:
            duration_ok = duration_seconds <= MAX_DURATION_SECONDS
            logger.info(f"Audio duration: {duration_seconds:.1f}s (limit: {MAX_DURATION_SECONDS}s, OK: {duration_ok})")
            
            if not duration_ok:
                shutil.rmtree(temp_path, ignore_errors=True)
                raise HTTPException(status_code=413, detail=f"Audio duration {duration_seconds:.0f}s exceeds maximum allowed {MAX_DURATION_SECONDS}s")
        else:
            logger.warning("Duration check skipped - could not determine duration")

        now_ts = time.time()

        # Local Pool Fallback
        if _process_pool is None:
             raise HTTPException(status_code=503, detail="Backend unavailable")

        job_id = uuid.uuid4().hex
        JOBS[job_id] = {
            "status": "pending",
            "model": separation_model,
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

        def _on_done(fut, job_id=job_id, model=separation_model):
            # Reload job to get latest state
            job = JOBS.get(job_id)
            if not job:
                return

            job["finished_at"] = time.time()
            try:
                res = fut.result()
                job["status"] = "done"
                job["result"] = res
                separations_total.labels(model=model, status="success").inc()
            except Exception as e:
                job["status"] = "error"
                job["error"] = str(e)
                separations_total.labels(model=model, status="error").inc()
                # Check for broken pool
                if "process pool is not usable" in str(e).lower() or "terminated abruptly" in str(e).lower():
                    logger.critical("🚨 Process Pool Broken! Triggering restart...")
                    _restart_process_pool()
            else:
                # ✅ Commit volume immediately after success
                _commit_modal_volume()
            finally:
                 try:
                    process_pool_busy.dec()
                    running_jobs.dec()
                 except: pass
            
            # Explicitly save back to trigger persistence
            JOBS[job_id] = job

        # Update job status to running and persist
        job = JOBS[job_id]
        job["status"] = "running"
        job["started_at"] = time.time()
        JOBS[job_id] = job
        
        # Check if process pool is available
        if _process_pool is None:
             _restart_process_pool()
             
        if _process_pool is None:
            job["status"] = "error"
            job["error"] = "Process pool not initialized"
            JOBS[job_id] = job
            shutil.rmtree(temp_path, ignore_errors=True)
            raise HTTPException(status_code=503, detail="Server not ready - process pool unavailable")
        
        try:
            process_pool_busy.inc()
            running_jobs.inc()
        except: pass
        
        try:
            future = _process_pool.submit(_worker_separate, separation_model, str(input_file), str(output_dir), SELECTED_DEVICE)
        except Exception as e:
            if "process pool is not usable" in str(e).lower() or "brokenprocesspool" in str(e).lower():
                logger.warning("⚠️ Pool broken during submission. Restarting and retrying...")
                _restart_process_pool()
                if _process_pool:
                    future = _process_pool.submit(_worker_separate, separation_model, str(input_file), str(output_dir), SELECTED_DEVICE)
                else:
                    raise HTTPException(status_code=503, detail="Backend unavailable after restart")
            else:
                raise e
        
        # Attach future to memory copy (JobManager handles this)
        job["future"] = future
        JOBS[job_id] = job
        
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


@app.post("/proxy/youtube-download")
async def proxy_youtube_download(request: dict):
    """Proxy endpoint to download YouTube audio using a community Cobalt instance"""
    import httpx
    
    # List of community instances to try (in case one is down)
    instances = [
        "https://cobalt.meowing.de/api/json",
        "https://api.cobalt.tools/api/json", # Official (might be down but worth keeping as backup)
    ]
    
    # Cobalt API payload
    payload = {
        "url": request.get("url"),
        "vCodec": "h264",
        "vQuality": "720",
        "aFormat": "mp3",
        "isAudioOnly": True,
        "filenamePattern": "basic"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for instance_url in instances:
            try:
                response = await client.post(
                    instance_url,
                    json=payload,
                    headers={
                        'Accept': 'application/json',
                        'Content-Type': 'application/json'
                    }
                )
                
                data = response.json()
                
                if data.get('status') in ['redirect', 'stream']:
                    return {
                        "status": "ok",
                        "url": data.get('url'),
                        "title": data.get('filename', 'audio')
                    }
                
            except Exception as e:
                logger.warning(f"Failed to reach cobalt instance {instance_url}: {e}")
                continue
                
    raise HTTPException(status_code=502, detail="Failed to download from all available Cobalt instances")


class YouTubeRequest(BaseModel):
    model_config = {"protected_namespaces": ()}  # Allow 'model_' prefix
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
    temp_path = TEMP_DIR / f"tmp{uuid.uuid4().hex[:12]}"
    temp_path.mkdir(parents=True, exist_ok=True)
    
    # Cleanup old sessions (limited to prevent slowdown)
    # cleanup_old_sessions(max_age_seconds=3600, max_to_check=20)
    
    output_dir = temp_path / "output"
    output_dir.mkdir(exist_ok=True)

    try:
        # Download YouTube (sync, but fast enough for now, or could be async)
        loop = asyncio.get_running_loop()
        input_file = await loop.run_in_executor(None, download_youtube_audio, yt_req.url, temp_path)
        
        file_size = input_file.stat().st_size
        
        # --- Reuse logic from 
        
        now_ts = time.time()
        
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

        def _on_done(fut, job_id=job_id, model=yt_req.model_name if 'yt_req' in locals() else model_name):
            # Reload job to get latest state (though we are updating it)
            job = JOBS.get(job_id)
            if not job:
                return

            job["finished_at"] = time.time()
            try:
                res = fut.result()
                job["status"] = "done"
                job["result"] = res
                separations_total.labels(model=model, status="success").inc()
            except Exception as e:
                job["status"] = "error"
                job["error"] = str(e)
                separations_total.labels(model=model, status="error").inc()
                
                # Check for broken pool
                if "process pool is not usable" in str(e).lower() or "terminated abruptly" in str(e).lower():
                    logger.critical("🚨 Process Pool Broken (YouTube)! Triggering restart...")
                    
                    # 🚑 RESCUE STRATEGY: Check if files actually exist
                    out_dir = Path(job.get("output_dir", ""))
                    if out_dir.exists():
                        stems = list(out_dir.glob("*.flac"))
                        # Get expected stem count from model config
                        expected_stems = len(STEM_CONFIGS.get(model, {}).get("stems", []))
                        min_stems = max(4, expected_stems)  # At least 4, or model's expected count
                        
                        if len(stems) >= min_stems:
                            logger.info(f"🚑 Rescue: Found {len(stems)} stems despite crash. Marking as DONE.")
                            job["status"] = "done"
                            job["error"] = None
                            # Reconstruct result dict
                            job["result"] = {s.stem: str(s) for s in stems}
                            separations_total.labels(model=model, status="rescued").inc()
                            _commit_modal_volume()
                        else:
                            logger.warning(f"🚑 Rescue failed: Only found {len(stems)} stems.")

                    _restart_process_pool()
            else:
                # ✅ Commit volume immediately after success
                _commit_modal_volume()
            finally:
                 try:
                    process_pool_busy.dec()
                    running_jobs.dec()
                 except: pass
            
            # Explicitly save back to trigger persistence
            JOBS[job_id] = job

        # Update job status to running and persist
        job = JOBS[job_id]
        job["status"] = "running"
        job["started_at"] = time.time()
        JOBS[job_id] = job
        
        # Check if process pool is available
        # Check if process pool is available
        if _process_pool is None:
             _restart_process_pool()
             
        if _process_pool is None:
            job["status"] = "error"
            job["error"] = "Process pool not initialized"
            JOBS[job_id] = job
            shutil.rmtree(temp_path, ignore_errors=True)
            raise HTTPException(status_code=503, detail="Server not ready - process pool unavailable")
        
        try:
            process_pool_busy.inc()
            running_jobs.inc()
        except: pass
        
        try:
            future = _process_pool.submit(_worker_separate, yt_req.model_name, str(input_file), str(output_dir), SELECTED_DEVICE)
        except Exception as e:
            if "process pool is not usable" in str(e).lower() or "brokenprocesspool" in str(e).lower():
                logger.warning("⚠️ Pool broken during submission (YouTube). Restarting and retrying...")
                _restart_process_pool()
                if _process_pool:
                     future = _process_pool.submit(_worker_separate, yt_req.model_name, str(input_file), str(output_dir), SELECTED_DEVICE)
                else:
                    raise HTTPException(status_code=503, detail="Backend unavailable after restart")
            else:
                raise e
        # Future cannot be persisted, but we keep it in memory dict via JobManager (it handles this)
        # Wait, JobManager.__setitem__ removes 'future' before saving to disk, but keeps it in memory!
        # So we can just set it on the dict in memory?
        # No, JOBS[job_id] returns a COPY if from disk.
        # If we want to attach future, we need to attach it to the memory copy?
        # JobManager logic:
        # __getitem__ checks disk. If found, returns loaded dict.
        # __setitem__ saves to disk AND updates _memory_jobs.
        
        # So:
        job["future"] = future
        JOBS[job_id] = job
        
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
        for stem, volume in req.stems.items():
            if volume > 0:
                # Look for OGG files 
                stem_path = session_path / f"{stem}.flac"
                if stem_path.exists():
                    data, sr = sf.read(str(stem_path))
                    
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

        output_mix = session_path / "mix.flac"
        sf.write(str(output_mix), mixed_audio, sr, format='FLAC', subtype='PCM_24')
        
        return FileResponse(
            path=str(output_mix),
            media_type="audio/flac",
            filename="mix.flac"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mixing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/download/{session_id}/{stem_name}")
def download_stem(session_id: str, stem_name: str):
    """
    Télécharge un stem spécifique
    """
    # Handle stem_name with or without extension
    clean_name = stem_name
    if clean_name.endswith(".flac"):
        clean_name = clean_name[:-4]
        
    file_path = TEMP_DIR / session_id / "output" / f"{clean_name}.flac"
    media_type = "audio/flac"
    filename = f"{clean_name}.flac"
    
    if not file_path.exists():
        logger.warning(
            f"Stem not found",
            extra={"session_id": session_id, "stem_name": stem_name}
        )
        raise HTTPException(
            status_code=404,
            detail=f"Fichier {stem_name}.flac non trouvé pour session {session_id}"
        )
    
    logger.info(
        f"Stem download",
        extra={"session_id": session_id, "stem_name": stem_name}
    )
    
    return NoRangeFileResponse(
        path=str(file_path),
        media_type="audio/flac",
        filename=f"{stem_name}.flac"
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
    
    return NoRangeFileResponse(
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
    resp = {k: v for k, v in job.items() if k != "future"}
    return resp


@app.get("/download/status/{job_id}/{stem_name}")
def download_by_job(job_id: str, stem_name: str):
    """Télécharge un stem pour un job donné (nouvel endpoint compatible)."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") != "done":
        raise HTTPException(status_code=409, detail=f"Job not finished (status={job.get('status')})")

    output_dir = job.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=500, detail="Job has no output directory")

    file_path = Path(output_dir) / f"{stem_name}.wav"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Stem not found for job")

    return NoRangeFileResponse(path=str(file_path), media_type="audio/wav", filename=f"{stem_name}.wav")


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




@app.post("/cleanup-on-exit")
def cleanup_on_exit():
    """
    Cleanup endpoint called when user closes the window.
    Performs more aggressive cleanup since user is leaving.
    """
    try:
        # Clean older sessions (2+ hours old) and check more
        cleaned = cleanup_old_sessions(max_age_seconds=7200, max_to_check=100)
        
        # Optionally clear model cache if no active jobs
        active_jobs = sum(1 for job in JOBS.values() if job.get("status") in ["pending", "running"])
        models_cleared = False
        if active_jobs == 0:
            loaded = list(get_separator.__globals__.get('_loaded_models', {}).keys())
            if len(loaded) > 0:
                logger.info(f"Clearing model cache on exit ({len(loaded)} models)")
                clear_cache()
                models_cleared = True
        
        return {
            "status": "success",
            "sessions_cleaned": cleaned,
            "models_cleared": models_cleared
        }
    except Exception as e:
        logger.error(f"Cleanup on exit failed: {e}")
        return {"status": "error", "detail": str(e)}


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
                
                # Update pending jobs metric
                try:
                    # Count jobs with status 'pending' or 'processing'
                    # Note: This iterates over all jobs, which might be slow if many jobs.
                    # In JobManager, we might need a more efficient way if persistence is huge.
                    # For now, we assume reasonable number of active jobs.
                    pending_count = 0
                    running_count = 0
                    
                    # If using file persistence, we can't easily iterate all without listing files.
                    # If using memory, we can.
                    # Let's just check memory jobs for now as a proxy for "active" jobs on this instance.
                    # Or better, if JobManager has a method to list active.
                    
                    # Since we can't easily list all files in JobManager without adding a method,
                    # we will skip this for file-based persistence for now to avoid I/O storm.
                    pass
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Error updating metrics in background thread: {e}")
            _metrics_stop_event.wait(_METRICS_INTERVAL)
        logger.info("Metrics updater thread stopped")

    if _metrics_thread is None or not _metrics_thread.is_alive():
        _metrics_thread = threading.Thread(target=_metrics_updater_loop, name="metrics_updater", daemon=True)
        _metrics_thread.start()

    # Create process pool for CPU-bound separation tasks
    try:
        # CRITICAL: Set spawn method for CUDA compatibility
        # Fork doesn't work with CUDA - must use spawn
        import multiprocessing
        multiprocessing.set_start_method('spawn', force=True)
        
        _process_pool = ProcessPoolExecutor(max_workers=_PROCESS_POOL_MAX_WORKERS)
        logger.info(f"ProcessPoolExecutor started with {_PROCESS_POOL_MAX_WORKERS} workers (spawn method)")
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