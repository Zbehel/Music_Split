FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

WORKDIR /app

# Installer dépendances système
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copier requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier code
COPY src/ ./src/
COPY .env .

# Télécharger modèle au build (évite download à chaque run)
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs')"

# Exposer port API
EXPOSE 8000

# Commande par défaut
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]