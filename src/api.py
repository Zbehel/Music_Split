from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
import tempfile
import shutil
from pathlib import Path
import uuid
from typing import Optional
from src.separator import MusicSeparator, list_available_models
from src.config import settings
import torchaudio

app = FastAPI(
    title="Music Separation API",
    description="Separate audio tracks into individual stems using deep learning",
    version="1.0.0"
)

# Stockage temporaire des résultats
RESULTS_DIR = Path(settings.results_dir)
RESULTS_DIR.mkdir(exist_ok=True)

# Cache de separators pour différents modèles
separator_cache = {}


def get_separator(model_name: str) -> MusicSeparator:
    """Get or create separator for a model"""
    if model_name not in separator_cache:
        separator_cache[model_name] = MusicSeparator(
            model_name=model_name,
            device=settings.device
        )
    return separator_cache[model_name]


@app.get("/")
def root():
    """API root"""
    return {
        "name": "Music Separation API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "device": settings.device,
        "default_model": settings.model_name
    }


@app.get("/models")
def list_models():
    """List all available separation models"""
    models = list_available_models()
    return {
        "models": models,
        "default": settings.model_name,
        "total": len(models)
    }


@app.get("/models/{model_name}/info")
def get_model_info(model_name: str):
    """Get information about a specific model"""
    try:
        separator = get_separator(model_name)
        return separator.info
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Model not found: {str(e)}")


@app.post("/separate")
async def separate_music(
    file: UploadFile = File(...),
    model_name: Optional[str] = Query(None, description="Model to use (default: htdemucs)"),
    output_format: Optional[str] = Query("wav", description="Output format (wav, mp3, flac)"),
    background_tasks: BackgroundTasks = None
):
    """
    Upload audio file and separate into stems
    
    Args:
        file: Audio file to separate
        model_name: Model to use (optional, defaults to config)
        output_format: Output format for stems
    
    Returns:
        Job ID and download URLs for stems
    """
    # Validate model
    model = model_name or settings.model_name
    available_models = list_available_models()
    if model not in available_models:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model '{model}'. Available: {available_models}"
        )
    
    # Validate file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset
    
    max_size_bytes = settings.max_file_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {settings.max_file_size_mb}MB"
        )
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith('audio/'):
        if not any(file.filename.endswith(ext) for ext in ['.mp3', '.wav', '.flac', '.ogg', '.m4a']):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Must be an audio file"
            )
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    job_dir = RESULTS_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    
    # Save uploaded file
    input_path = job_dir / f"input{Path(file.filename).suffix}"
    try:
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Validate audio duration (optional check)
    try:
        info = torchaudio.info(str(input_path))
        duration = info.num_frames / info.sample_rate
        if duration > settings.max_duration_seconds:
            raise HTTPException(
                status_code=413,
                detail=f"Audio too long. Max duration: {settings.max_duration_seconds}s"
            )
    except Exception as e:
        # If we can't read the file, let the separator handle it
        pass
    
    # Separate (synchronous for now)
    try:
        separator = get_separator(model)
        results = separator.separate(
            str(input_path),
            str(job_dir),
            save_format=output_format
        )
        
        return {
            "job_id": job_id,
            "status": "completed",
            "model": model,
            "stems": {
                stem: f"/download/{job_id}/{Path(path).name}"
                for stem, path in results.items()
            },
            "info": separator.info
        }
    except Exception as e:
        # Cleanup on error
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail=f"Separation failed: {str(e)}"
        )


@app.get("/download/{job_id}/{filename}")
def download_stem(job_id: str, filename: str):
    """Download separated stem"""
    file_path = RESULTS_DIR / job_id / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Security: ensure path is within RESULTS_DIR
    if not str(file_path.resolve()).startswith(str(RESULTS_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return FileResponse(
        path=str(file_path),
        media_type=f"audio/{file_path.suffix[1:]}",
        filename=filename
    )


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """Check job status"""
    job_dir = RESULTS_DIR / job_id
    
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    
    stems = [f for f in job_dir.glob("*") if f.suffix in ['.wav', '.mp3', '.flac']]
    stems = [f for f in stems if not f.name.startswith('input')]
    
    return {
        "job_id": job_id,
        "status": "completed" if stems else "processing",
        "stems_count": len(stems),
        "files": [f.name for f in stems]
    }


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """Delete job and its results"""
    job_dir = RESULTS_DIR / job_id
    
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    
    try:
        shutil.rmtree(job_dir)
        return {"status": "deleted", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
