#!/bin/bash
set -e

# Check if API_URL is set
if [ -z "$API_URL" ]; then
    echo "WARNING: API_URL is not set. The frontend might not connect to the backend."
    echo "Usage: API_URL=https://your-modal-app.modal.run ./deploy.sh"
fi

# Navigate to web directory
cd ../../web

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm ci
fi

# Build
echo "Building frontend..."
# Pass API_URL to build
VITE_API_URL=$API_URL npm run build

# Deploy
echo "Deploying to Cloudflare..."
cd ../deploy/cloudflare
npx wrangler pages deploy ../../web/dist --project-name music-split-frontend
