FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

WORKDIR /app

# Installer dépendances système
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copier requirements
COPY requirements.txt .
# Use the Python executable to run pip to ensure packages install into the same environment
RUN python -m pip install --upgrade pip setuptools wheel || true
RUN ( /opt/conda/bin/python -m pip install --no-cache-dir -r requirements.txt ) || \
    ( python -m pip install --no-cache-dir -r requirements.txt ) || \
    ( echo "Primary pip install failed, retrying specific packages with conda/python pip" && /opt/conda/bin/python -m pip install --no-cache-dir celery redis prometheus-client || python -m pip install --no-cache-dir celery redis prometheus-client )

# Copier code
COPY src/ ./src/

# Variables d'environnement par défaut (peuvent être surchargées)
ENV MODEL_NAME=htdemucs
ENV DEVICE=cpu
ENV API_HOST=0.0.0.0
ENV API_PORT=8000
ENV MAX_FILE_SIZE_MB=100
ENV MAX_DURATION_SECONDS=600


# Commande par défaut
# Commande par défaut (supporte la variable PORT injectée par Cloud Run)
CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000}"]