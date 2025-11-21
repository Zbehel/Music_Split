# GKE Autopilot Deployment Walkthrough

## 1. Prerequisites
Ensure you have the Google Cloud SDK installed and authenticated:
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud auth configure-docker europe-west1-docker.pkg.dev
```

## 2. Build and Push Docker Image
I created a script to automate this. Run:
```bash
./scripts/build_and_push.sh
```
This will build the image and push it to `europe-west1-docker.pkg.dev/YOUR_PROJECT_ID/music-separator/api:latest`.

## 3. Create GKE Cluster
You need a Kubernetes cluster to run your pods. Run this command to create an Autopilot cluster (managed, easier):
```bash
gcloud container clusters create-auto music-cluster \
    --region europe-west1 \
    --project zmusic-split
```
*This will take 5-10 minutes.*

## 4. Deploy to GKE
**Important**: Before deploying, you must update the `image` field in [k8s/gke-autopilot.yaml](file:///Users/zac/Documents/Projets/Music_Split/k8s/gke-autopilot.yaml) with your actual Project ID. You need to do this in **two places** (for the API and for the Worker).

1. Open [k8s/gke-autopilot.yaml](file:///Users/zac/Documents/Projets/Music_Split/k8s/gke-autopilot.yaml).
2. Find the lines: `image: europe-west1-docker.pkg.dev/YOUR_PROJECT_ID/music-separator/api:latest`
3. Replace `YOUR_PROJECT_ID` with your actual Google Cloud Project ID in both occurrences.

Then apply the manifest:
```bash
kubectl apply -f k8s/gke-autopilot.yaml
```

## 5. Accessing the API & Logs

### Get the External IP
To access your API from the internet, you need the external IP of the Load Balancer:
```bash
kubectl get service music-separator-service --watch
```
Wait until the `EXTERNAL-IP` changes from `<pending>` to an IP address (e.g., `34.x.x.x`).
Then you can access it at: `http://YOUR_EXTERNAL_IP/docs`

### View Logs
To see what's happening inside your containers:

**API Logs:**
```bash
# List pods to get the exact name
kubectl get pods

# View logs (replace pod name)
kubectl logs music-separator-api-xxxxx-xxxxx
# Follow logs in real-time
kubectl logs -f deployment/music-separator-api
```

**Worker Logs:**
```bash
kubectl logs -f deployment/music-separator-worker
```

## 6. Shutdown (Stop Costs)
To stop the running pods (and stop paying for CPU/RAM) but keep the cluster and IP:
```bash
kubectl delete -f k8s/gke-autopilot.yaml
```

## 7. Cleanup (Delete Everything)
To completely remove everything and stop all billing:

1. **Delete the Cluster**:
```bash
gcloud container clusters delete music-cluster --region europe-west1 --quiet
```

2. **Delete the Repository** (Optional, to save storage costs):
```bash
gcloud artifacts repositories delete music-separator --location=europe-west1 --quiet
```

3. **Delete the Project** (Optional, nuclear option):
```bash
gcloud projects delete zmusic-split --quiet
```
