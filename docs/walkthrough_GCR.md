# Cloud Run Deployment Walkthrough

## 1. Prerequisites
Ensure you have the Google Cloud SDK installed and authenticated:
```bash
gcloud auth login
gcloud config set project Music Split
gcloud auth configure-docker europe-west1-docker.pkg.dev
```

## 2. Build and Deploy
I created a script to automate the entire build and deployment process. Run:
```bash
./deploy/cloud-run/deploy.sh
```
This will:
1. Create the Artifact Registry repository if it doesn't exist.
2. Build the Docker image and push it to `europe-west1-docker.pkg.dev/Music Split/music-separator-repo/music-separator-api:latest`.
3. Deploy the service to Cloud Run with **NVIDIA L4 GPU** configuration.

## 3. Accessing the API
Once the script finishes, it will output the Service URL. You can also retrieve it with:
```bash
gcloud run services describe Music Split --region europe-west1 --format 'value(status.url)'
```
Example output: `https://Music Split-xyz-ew.a.run.app`

### Health Check
```bash
SERVICE_URL=$(gcloud run services describe Music Split --region europe-west1 --format 'value(status.url)')
curl $SERVICE_URL/health
```

## 4. Monitoring & Logs
Cloud Run has built-in monitoring.

### View Logs
To see what's happening inside your containers:
```bash
# Tail logs in real-time
gcloud beta run services logs tail Music Split --region europe-west1

# Read recent logs
gcloud beta run services logs read Music Split --region europe-west1 --limit 50
```

### View Metrics
1. Go to the [Cloud Run Console](https://console.cloud.google.com/run).
2. Select `Music Split`.
3. Click the **Metrics** tab to see:
    *   **Container instance count**: Watch it scale to 0 when idle.
    *   **GPU utilization**: Check if the GPU is being used.

## 5. Shutdown (Stop Costs)
Cloud Run automatically scales to zero when idle, so you don't *need* to delete the service to stop costs. However, to remove the service entirely:
```bash
gcloud run services delete Music Split --region europe-west1 --quiet
```

## 6. Cleanup (Delete Everything)
To completely remove everything and stop all billing:

1. **Delete the Service**:
```bash
gcloud run services delete Music Split --region europe-west1 --quiet
```

2. **Delete the Repository** (Optional, to save storage costs):
```bash
gcloud artifacts repositories delete music-separator-repo --location=europe-west1 --quiet
```

3. **Delete the Project** (Optional, nuclear option):
```bash
gcloud projects delete Music Split --quiet
```
