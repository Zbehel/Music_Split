# Deployment Guide

This document lists the commands to deploy the Music Split application using various methods.

## 1. Modal.com (API & Monitoring)

Modal is used to host the Python FastAPI backend, including GPU-accelerated separation tasks and monitoring tools.

### Prerequisites
- Install Modal: `pip install modal`
- Authenticate: `modal setup`

### Commands

**Deploy API:**
```bash
modal deploy deploy/modal/modal_app.py
```
*Builds the Docker image defined in `deploy/docker/Dockerfile`, mounts the `src/` directory, and deploys the FastAPI app to Modal's serverless infrastructure with GPU support.*

**Serve API (Dev Mode):**
```bash
modal serve deploy/modal/modal_app.py
```
*Runs the app in "dev" mode with hot-reloading. Changes to local files are automatically synced.*

**Deploy Monitoring (Prometheus & Grafana):**
```bash
modal deploy deploy/modal/monitoring.py
```
*Deploys Prometheus and Grafana instances on Modal. Prometheus scrapes metrics from your API, and Grafana provides a dashboard. Uses `modal.Volume` for data persistence.*

---

## 2. Cloudflare Pages (Frontend)

Cloudflare Pages hosts the React frontend.

### Prerequisites
- Install Wrangler: `npm install -g wrangler`
- Authenticate: `npx wrangler login`

### Commands

**Deploy Frontend:**
```bash
# Set your API URL first!
export API_URL="https://<your-modal-app-url>"

cd deploy/cloudflare
./deploy.sh
```
*This script performs two steps:*
1.  *Builds the React app (`npm run build` in `web/`), injecting the `API_URL` into the build.*
2.  *Uploads the `web/dist` folder to Cloudflare Pages using `wrangler`.*

---

## 3. Local Development

Run the full stack locally.

### Backend
```bash
# Using the local environment
uvicorn src.api:app --reload

# OR using Docker
docker build -t music-split-api -f deploy/docker/Dockerfile .
docker run -p 8000:8000 music-split-api
```

### Frontend
```bash
cd web
npm run dev
```

---

## 4. Google Cloud Run (Alternative)

*Note: This method requires Google Cloud SDK (`gcloud`) and a configured GCP project.*

**Deploy API & Frontend:**
```bash
./scripts/deploy_cloud_run.sh
```
*Builds Docker images for both API and Frontend, pushes them to Google Container Registry (GCR), and deploys them to Cloud Run. It also configures the frontend to talk to the API.*
