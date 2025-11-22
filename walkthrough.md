# Deployment Walkthrough

This guide explains how to deploy the Music Split API to Modal.com and the Frontend to Cloudflare Pages.

## Prerequisites

- [Modal Account](https://modal.com)
- [Cloudflare Account](https://dash.cloudflare.com)
- `npm` installed

## 1. Install Deployment Tools

```bash
pip install -r deploy/requirements.txt
npm install -g wrangler
```

## 2. Setup Modal

Authenticate with Modal:

```bash
modal setup
```

## 3. Deploy API & Monitoring

### Deploy the API

```bash
modal deploy deploy/modal/modal_app.py
```

Note the URL of the deployed API (e.g., `https://<username>--music-split-api-fastapi-app.modal.run`).

### Configure Prometheus

Edit `deploy/modal/prometheus.yml` and replace `REPLACE_WITH_YOUR_API_URL_WITHOUT_HTTPS` with your API host (e.g., `<username>--music-split-api-fastapi-app.modal.run`).

### Deploy Monitoring (Prometheus & Grafana)

```bash
modal deploy deploy/modal/monitoring.py
```

This will deploy Prometheus and Grafana. You can access them via the URLs provided by Modal.

## 4. Deploy Frontend

Deploy the frontend to Cloudflare Pages, pointing it to your Modal API.

```bash
# Replace with your actual API URL
export API_URL="https://<username>--music-split-api-fastapi-app.modal.run"

cd deploy/cloudflare
./deploy.sh
```

## 5. Verification

1. Open the Cloudflare Pages URL.
2. Upload a file or use a YouTube link.
3. Verify that the separation job starts and completes.
4. Check Grafana (default login `admin`/`admin` - you might need to configure this or use the default) to see metrics.
