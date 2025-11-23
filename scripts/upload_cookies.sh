#!/bin/bash
# Upload YouTube cookies to Modal volume

set -e

COOKIES_FILE="www.youtube.com_cookies.txt"
VOLUME_NAME="music-split-jobs-data"
REMOTE_PATH="/youtube_cookies.txt"

# Check if cookies file exists
if [ ! -f "$COOKIES_FILE" ]; then
    echo "❌ Error: $COOKIES_FILE not found in current directory"
    echo "Please export cookies from your browser first"
    exit 1
fi

echo "📤 Uploading $COOKIES_FILE to Modal volume..."
modal volume put -f "$VOLUME_NAME" "$COOKIES_FILE" "$REMOTE_PATH"

echo "✅ Cookies uploaded successfully!"
echo "🔍 Verifying upload..."
modal volume ls "$VOLUME_NAME" /

echo ""
echo "✨ Done! YouTube downloads should now work on Modal."
