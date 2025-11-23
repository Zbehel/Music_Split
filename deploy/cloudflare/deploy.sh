#!/bin/bash
set -e

# Check if API_URL is set, otherwise use default
if [ -z "$API_URL" ]; then
    API_URL="https://zbehel--music-split-api-fastapi-app.modal.run"
    echo "ℹ️ Using default API_URL: $API_URL"
fi

# Navigate to web directory
cd "$(dirname "$0")/../../web"

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
