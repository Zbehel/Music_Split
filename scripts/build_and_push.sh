#!/bin/bash
set -e

# Configuration
PROJECT_ID=$(gcloud config get-value project)
REGION="europe-west1" # Change this if needed
REPO_NAME="music-separator"
IMAGE_NAME="api"
TAG="latest"

if [ -z "$PROJECT_ID" ]; then
    echo "Error: No Google Cloud project selected."
    echo "Run 'gcloud config set project music-split' first."
    exit 1
fi

FULL_IMAGE_NAME="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:$TAG"

echo "🚀 Building Docker image..."
docker build --platform linux/amd64 -t $FULL_IMAGE_NAME .

echo "☁️  Pushing to Artifact Registry..."
# Ensure authentication
gcloud auth configure-docker $REGION-docker.pkg.dev --quiet

docker push $FULL_IMAGE_NAME

echo "✅ Done! Image pushed to: $FULL_IMAGE_NAME"
