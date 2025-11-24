FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
# git and build-essential are often needed for pip installs
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy code
COPY src/ ./src/

# Env vars
ENV MODEL_NAME=htdemucs
ENV DEVICE=cuda
ENV API_HOST=0.0.0.0
ENV API_PORT=8000
ENV MAX_FILE_SIZE_MB=100
ENV MAX_DURATION_SECONDS=600

# Default command
CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000}"]