from fastapi import FastAPI, File, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import tempfile
import shutil
from pathlib import Path
import uuid
from src.separator import MusicSeparator

app = FastAPI(title="Music Separation API")
separator = MusicSeparator()

# Stockage temporaire des résultats
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

@app.get("/health")
def health_check():
    return {"status": "healthy", "device": separator.device}

@app.post("/separate")
async def separate_music(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    Upload audio file and separate into stems
    Returns job_id to retrieve results
    """
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    job_dir = RESULTS_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    
    # Save uploaded file
    input_path = job_dir / "input.audio"
    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    # Separate (synchronous for now)
    try:
        results = separator.separate(
            str(input_path),
            str(job_dir)
        )
        
        return {
            "job_id": job_id,
            "status": "completed",
            "stems": {
                stem: f"/download/{job_id}/{stem}.wav"
                for stem in results.keys()
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.get("/download/{job_id}/{stem}")
def download_stem(job_id: str, stem: str):
    """Download separated stem"""
    file_path = RESULTS_DIR / job_id / f"{stem}.wav"
    
    if not file_path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": "File not found"}
        )
    
    return FileResponse(
        path=str(file_path),
        media_type="audio/wav",
        filename=f"{stem}.wav"
    )

@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """Check job status"""
    job_dir = RESULTS_DIR / job_id
    
    if not job_dir.exists():
        return JSONResponse(
            status_code=404,
            content={"error": "Job not found"}
        )
    
    stems = list(job_dir.glob("*.wav"))
    
    return {
        "job_id": job_id,
        "status": "completed" if stems else "processing",
        "stems_count": len(stems)
    }