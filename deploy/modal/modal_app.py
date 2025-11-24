import modal
import os
import sys
from pathlib import Path

# Define the image natively for faster builds
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "libsndfile1", "git", "build-essential")
    .pip_install_from_requirements(
        "requirements.txt",
        extra_index_url="https://download.pytorch.org/whl/cu121"
    )
    .add_local_dir("src", remote_path="/app/src")
)

app = modal.App("music-split-api", image=image)

# Define volumes for caching models to avoid redownloading
hf_volume = modal.Volume.from_name("music-split-hf-cache", create_if_missing=True)
torch_volume = modal.Volume.from_name("music-split-torch-cache", create_if_missing=True)
jobs_volume = modal.Volume.from_name("music-split-jobs-data", create_if_missing=True)

@app.function(
    image=image,
    gpu="T4", # Use T4 for cost effectiveness, or A10G for speed
    memory=8192, # Increase memory to 8GB to prevent OOM
    timeout=600, # 10 minutes
    volumes={
        "/root/.cache/huggingface": hf_volume,
        "/root/.cache/torch": torch_volume,
        "/data": jobs_volume
    },
    env={"JOBS_DIR": "/data/jobs", "SESSIONS_DIR": "/data/sessions"},
    max_containers=1,
    secrets=[modal.Secret.from_dotenv()] # Load env vars
)
@modal.asgi_app()
def fastapi_app():
    # Import here to ensure it runs inside the container
    sys.path.append("/app")
    from src.api import app
    return app
