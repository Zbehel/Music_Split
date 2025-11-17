"""
FastAPI backend pour Music Source Separator
Support Demucs + MVSEP models
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Dict, List, Optional
import tempfile
import shutil
import logging
from datetime import datetime

from src.separator import get_separator, clear_cache, MusicSeparator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Créer l'application FastAPI
app = FastAPI(
    title="Music Source Separator API",
    description="Sépare les pistes audio avec Demucs et MVSEP",
    version="2.0.0"
)

# CORS pour Gradio
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dossier temporaire pour les résultats
TEMP_DIR = Path("/tmp/music-separator")
TEMP_DIR.mkdir(exist_ok=True)


@app.get("/")
def root():
    """Page d'accueil"""
    return {
        "message": "Music Source Separator API v2.0",
        "docs": "/docs",
        "health": "/health",
        "models": "/models"
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    from src.separator import get_best_device
    import torch
    
    device = get_best_device()
    device_info = {
        "current": device,
        "cuda_available": torch.cuda.is_available(),
        "mps_available": hasattr(torch.backends, 'mps') and torch.backends.mps.is_available() if hasattr(torch.backends, 'mps') else False,
    }
    
    return {
        "status": "healthy",
        "device": device,
        "device_info": device_info,
        "models_loaded": list(get_separator.__globals__.get('_loaded_models', {}).keys()),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/models")
def get_models():
    """Liste des modèles disponibles"""
    models = MusicSeparator.get_available_models()
    
    return {
        "models": list(models.keys()),
        "details": models
    }


@app.get("/models/{model_name}")
def get_model_info(model_name: str):
    """Info sur un modèle spécifique"""
    try:
        info = MusicSeparator.get_model_info(model_name)
        return info
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/separate")
async def separate_audio(
    file: UploadFile = File(...),
    model_name: str = Form(default="htdemucs_6s")
):
    """
    Sépare un fichier audio en stems
    
    Args:
        file: Fichier audio (WAV, MP3, FLAC, etc.)
        model_name: Modèle à utiliser (htdemucs_6s, htdemucs_ft, mvsep_full)
        
    Returns:
        JSON avec chemins des stems générés
    """
    logger.info(f"Nouvelle requête de séparation avec modèle: {model_name}")
    
    # Vérifier que le modèle existe
    if model_name not in MusicSeparator.AVAILABLE_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Modèle '{model_name}' non disponible. "
                   f"Choisir parmi: {list(MusicSeparator.AVAILABLE_MODELS.keys())}"
        )
    
    # Créer un dossier temporaire unique
    temp_session = tempfile.mkdtemp(dir=TEMP_DIR)
    temp_path = Path(temp_session)
    
    try:
        # Sauvegarder le fichier uploadé
        input_file = temp_path / "input.wav"
        with input_file.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        
        logger.info(f"Fichier sauvegardé: {input_file}")
        
        # Créer le dossier de sortie
        output_dir = temp_path / "output"
        output_dir.mkdir(exist_ok=True)
        
        # Récupérer le séparateur (avec cache)
        separator = get_separator(model_name)
        
        # Séparer l'audio
        logger.info("Début de la séparation...")
        results = separator.separate(str(input_file), str(output_dir))
        
        logger.info(f"Séparation terminée: {len(results)} stems générés")
        
        # Retourner les chemins des fichiers
        return {
            "status": "success",
            "model_used": model_name,
            "stems_count": len(results),
            "stems": results,
            "session_id": temp_path.name
        }
        
    except Exception as e:
        logger.error(f"Erreur lors de la séparation: {str(e)}")
        # Nettoyer en cas d'erreur
        shutil.rmtree(temp_path, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{session_id}/{stem_name}")
def download_stem(session_id: str, stem_name: str):
    """
    Télécharge un stem spécifique
    
    Args:
        session_id: ID de session (nom du dossier temp)
        stem_name: Nom du stem (ex: "vocals", "drums")
    """
    file_path = TEMP_DIR / session_id / "output" / f"{stem_name}.wav"
    
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Fichier {stem_name}.wav non trouvé"
        )
    
    return FileResponse(
        path=str(file_path),
        media_type="audio/wav",
        filename=f"{stem_name}.wav"
    )


@app.post("/clear-cache")
def clear_model_cache():
    """Vide le cache des modèles chargés"""
    clear_cache()
    return {"status": "cache cleared"}


@app.delete("/cleanup/{session_id}")
def cleanup_session(session_id: str):
    """
    Nettoie les fichiers temporaires d'une session
    
    Args:
        session_id: ID de session à nettoyer
    """
    session_path = TEMP_DIR / session_id
    
    if session_path.exists():
        shutil.rmtree(session_path)
        return {"status": "cleaned", "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail="Session non trouvée")


@app.post("/cleanup-all")
def cleanup_all():
    """Nettoie tous les fichiers temporaires"""
    count = 0
    for item in TEMP_DIR.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
            count += 1
    
    return {"status": "all cleaned", "sessions_removed": count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)