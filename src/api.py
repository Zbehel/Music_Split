"""
FastAPI backend pour Music Source Separator v2.1
WITH: Monitoring, Structured Logging, Resilience Patterns
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Dict, Optional
import tempfile
import shutil
import time
from datetime import datetime
import asyncio

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
    
    # Generate request ID
    request_id = f"{datetime.now().timestamp()}-{id(request)}"
    
    # Create logger with context
    request_logger = get_logger(__name__, {"request_id": request_id})
    
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
    
    return response


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info("🚀 Music Separator API starting up")
    
    # Start background task to update system metrics
    asyncio.create_task(update_metrics_periodically())
    
    logger.info(f"Device: {get_best_device()}")
    logger.info(f"Available models: {list(STEM_CONFIGS.keys())}")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("🛑 Music Separator API shutting down")
    
    # Clear model cache
    clear_cache()


async def update_metrics_periodically():
    """Background task to update system metrics every 15 seconds"""
    while True:
        try:
            update_system_metrics()
            update_temp_storage_metrics(str(TEMP_DIR))
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
        
        await asyncio.sleep(15)


# ============================================================
# ENDPOINTS
# ============================================================

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
            "filename": file.filename,
            "client_ip": client_ip
        }
    )
    
    # ✅ Check model exists
    if model_name not in STEM_CONFIGS:
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
    
    # Créer un dossier temporaire unique
    temp_session = tempfile.mkdtemp(dir=TEMP_DIR)
    temp_path = Path(temp_session)
    
    try:
        # Sauvegarder le fichier uploadé
        input_file = temp_path / "input.wav"
        file_size = 0
        
        with input_file.open("wb") as f:
            content = await file.read()
            file_size = len(content)
            f.write(content)
        
        # Track file size
        separation_file_size_bytes.observe(file_size)
        
        logger.info(
            f"File saved",
            extra={
                "file_path": str(input_file),
                "file_size_bytes": file_size,
                "session_id": temp_path.name
            }
        )
        
        # Créer le dossier de sortie
        output_dir = temp_path / "output"
        output_dir.mkdir(exist_ok=True)
        
        # ✅ Get separator with circuit breaker
        try:
            @model_circuit_breaker.call
            def get_separator_safe():
                return get_separator(model_name)
            
            separator = get_separator_safe()
        except CircuitBreakerOpen:
            logger.error("Circuit breaker open for model loading")
            raise HTTPException(
                status_code=503,
                detail="Model service temporarily unavailable. Try again later."
            )
        
        # ✅ Separate audio with retry
        separation_start = time.time()
        
        @retry(max_attempts=2, delay=1.0, exceptions=(Exception,))
        def separate_with_retry():
            return separator.separate(str(input_file), str(output_dir))
        
        try:
            results = separate_with_retry()
        except RetryExhausted as e:
            logger.error(f"Separation failed after retries: {e}")
            separations_total.labels(
                model=model_name,
                status="error"
            ).inc()
            raise HTTPException(status_code=500, detail="Separation failed after retries")
        
        separation_duration = time.time() - separation_start
        
        # ✅ Update metrics
        separations_total.labels(
            model=model_name,
            status="success"
        ).inc()
        
        separation_duration_seconds.labels(
            model=model_name
        ).observe(separation_duration)
        
        # ✅ Structured logging
        log_separation(
            logger,
            model=model_name,
            audio_duration=0,  # Could calculate from file if needed
            processing_duration=separation_duration,
            status="success",
            session_id=temp_path.name,
            stems_count=len(results),
            file_size_bytes=file_size
        )
        
        logger.info(
            f"Separation completed",
            extra={
                "model": model_name,
                "stems_count": len(results),
                "duration_seconds": separation_duration,
                "session_id": temp_path.name
            }
        )
        
        # Retourner les chemins des fichiers
        return {
            "status": "success",
            "model_used": model_name,
            "stems_count": len(results),
            "stems": results,
            "session_id": temp_path.name,
            "processing_time_seconds": separation_duration
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error during separation",
            extra={
                "model": model_name,
                "error": str(e),
                "session_id": temp_path.name
            },
            exc_info=True
        )
        
        # Update error metrics
        errors_total.labels(
            type=type(e).__name__,
            endpoint="/separate"
        ).inc()
        
        separations_total.labels(
            model=model_name,
            status="error"
        ).inc()
        
        # Nettoyer en cas d'erreur
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)