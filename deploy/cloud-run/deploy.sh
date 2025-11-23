#!/bin/bash
set -e

# Ensure we are in the project root
cd "$(dirname "$0")/../.."
PROJECT_ROOT=$(pwd)

# Load .env if exists
if [ -f .env ]; then
  export $(cat .env | xargs)
fi

# Configuration
PROJECT_ID="zmusic-split-new"
REGION="europe-west1"
SERVICE_NAME="music-separator-service"
IMAGE_NAME="music-separator-api"
REPO_NAME="music-separator-repo"
IMAGE_TAG="latest"
ARTIFACT_REGISTRY_HOST="$REGION-docker.pkg.dev"
FULL_IMAGE_NAME="$ARTIFACT_REGISTRY_HOST/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:$IMAGE_TAG"

echo "🚀 Starting Cloud Run Deployment for $SERVICE_NAME..."

# 0. Ensure Artifact Registry Repo Exists
echo "🔍 Checking Artifact Registry repository..."
if ! gcloud artifacts repositories describe $REPO_NAME --location=$REGION --project=$PROJECT_ID > /dev/null 2>&1; then
    echo "📦 Creating Artifact Registry repository '$REPO_NAME'..."
    gcloud artifacts repositories create $REPO_NAME \
        --repository-format=docker \
        --location=$REGION \
        --description="Docker repository for Music Separator" \
        --project=$PROJECT_ID
else
    echo "✅ Repository '$REPO_NAME' already exists."
fi

# 1. Build and Push Docker Image
if [ "$SKIP_API_DEPLOY" != "true" ]; then
    echo "📦 Building and Pushing Docker image..."
    gcloud builds submit --tag $FULL_IMAGE_NAME . --project=$PROJECT_ID
else
    echo "⏩ Skipping API image build (SKIP_API_DEPLOY=true)..."
fi

# 2. Deploy to Cloud Run
# ====================================================
# 1. DEPLOY API (Backend)
# ====================================================

if [ "$SKIP_API_DEPLOY" = "true" ]; then
    echo "⏩ Skipping API deployment (SKIP_API_DEPLOY=true)..."
    if [ -z "$API_URL" ]; then
        echo "❌ Error: API_URL must be set when skipping API deployment."
        exit 1
    fi
    echo "ℹ️ Using provided API URL: $API_URL"
else
    echo "🚀 Deploying API to Cloud Run..."

    # Submit build to Cloud Build
    gcloud builds submit --tag $FULL_IMAGE_NAME .

    # Deploy to Cloud Run
    # Reduced max-instances to 2 to fit 40GB quota (2 * 16GB = 32GB)
    gcloud run deploy $SERVICE_NAME \
      --image $FULL_IMAGE_NAME \
      --platform managed \
      --region $REGION \
      --allow-unauthenticated \
      --port 8000 \
      --memory 16Gi \
      --cpu 4 \
      --no-cpu-throttling \
      --min-instances 0 \
      --max-instances 2 \
      --set-env-vars=MAX_FILE_SIZE_MB=200,MAX_DURATION_SECONDS=900,METRICS_PUBLISH_INTERVAL=15,model_name=htdemucs_6s \
      --gpu 1 \
      --gpu-type nvidia-l4

    # Capture API URL
    API_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)')
    echo "✅ API Deployed at: $API_URL"
fi

# ====================================================
# 2. DEPLOY FRONTEND (React)
# ====================================================
FRONTEND_SERVICE_NAME="music-separator-web"
FRONTEND_IMAGE_NAME="music-separator-web"
FRONTEND_IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$FRONTEND_IMAGE_NAME:$IMAGE_TAG"

echo "🚀 Building and Deploying Frontend..."
echo "   (Linking to API: $API_URL)"

# Build Frontend with API URL
# We use cloudbuild.yaml to pass the build argument
gcloud builds submit web \
  --config web/cloudbuild.yaml \
  --substitutions=_IMAGE_URI="$FRONTEND_IMAGE_URI",_VITE_API_URL="$API_URL"

# Deploy Frontend (Cheap CPU service)
gcloud run deploy $FRONTEND_SERVICE_NAME \
  --image $FRONTEND_IMAGE_URI \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --cpu 1

FRONTEND_URL=$(gcloud run services describe $FRONTEND_SERVICE_NAME --region $REGION --format 'value(status.url)')

echo "🎉 DEPLOYMENT COMPLETE!"
echo "------------------------------------------------"
echo "📱 Frontend: $FRONTEND_URL"
echo "🔌 API:      $API_URL"
echo "------------------------------------------------"
