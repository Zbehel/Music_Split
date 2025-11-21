# Web Interface & API Update Plan

## Goal
Replace the Gradio interface with a custom React-based web application that communicates with the FastAPI backend.

## User Review Required
> [!IMPORTANT]
> This change involves creating a new `web/` directory for the frontend and modifying [src/api.py](file:///Users/zac/Documents/Projets/Music_Split/src/api.py) to include business logic previously in [app.py](file:///Users/zac/Documents/Projets/Music_Split/app.py) (YouTube downloading).

## Proposed Changes

### Backend ([src/api.py](file:///Users/zac/Documents/Projets/Music_Split/src/api.py))
#### [MODIFY] [api.py](file:///Users/zac/Documents/Projets/Music_Split/src/api.py)
- Add `yt_dlp` integration.
- Add `POST /separate/youtube`: Accepts URL, downloads audio, then triggers separation.
- Add `POST /mix`: Accepts `session_id` and list of [stems](file:///Users/zac/Documents/Projets/Music_Split/src/api.py#723-783) to mix. Returns a merged WAV file.
- **GPU Support**:
    - Add `nodeSelector` and `resources` to [k8s/gke-autopilot.yaml](file:///Users/zac/Documents/Projets/Music_Split/k8s/gke-autopilot.yaml) to request NVIDIA T4 GPUs.
    - Update `deployment` to use `nvidia.com/gpu: 1`.

### Frontend (`web/`)
#### [NEW] React Application
- **Tech Stack**: React, Vite, TailwindCSS (via CDN or standard CSS if preferred), Lucide Icons.
- **Components**:
    - [App.jsx](file:///Users/zac/Documents/Projets/Music_Split/web/src/App.jsx): Main layout.
    - `InputSection.jsx`: File upload and YouTube URL input.
    - `AudioPlayer.jsx`: Master controls (Play/Pause/Stop, Seek).
    - `StemList.jsx`: List of stems with individual Mute/Volume controls.
    - `StemRow.jsx`: Individual stem player.
- **Logic**:
    - Port the "Audio Sync" logic from [app.py](file:///Users/zac/Documents/Projets/Music_Split/app.py) to a React Hook [useAudioSync](file:///Users/zac/Documents/Projets/Music_Split/web/src/useAudioSync.js#3-106).

### Deployment (`Cloud Run`)
#### [NEW] [scripts/deploy_cloud_run.sh](file:///Users/zac/Documents/Projets/Music_Split/scripts/deploy_cloud_run.sh)
- Script to build and deploy to Cloud Run.
- **Configuration**:
    - Region: `us-central1` (Required for L4 GPU)
    - GPU: `nvidia-l4`
    - Count: `1`
    - Memory: `16Gi` (Minimum for GPU)
    - CPU: `4` (Minimum for GPU)
    - Scaling: Min `0`, Max `5` (Scale to Zero enabled by default)

### Monitoring
- Use built-in Google Cloud Monitoring and Logging.
- (Optional) Deploy a standalone Grafana on Cloud Run if custom dashboards are strictly needed, but Console is usually sufficient.


## Verification Plan
### Automated Tests
- Test API endpoints (`/separate/youtube`, `/mix`) using `curl` or `pytest`.
### Manual Verification
- Launch Web App (`npm run dev`).
- Test YouTube flow.
- Test File Upload flow.
- Verify Sync Player works (audio stays in sync).
- Verify Mix download works.
